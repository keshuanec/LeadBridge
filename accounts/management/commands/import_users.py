"""
Management command pro import uživatelů z XLSX souboru.

Použití:
    python manage.py import_users <cesta_k_xlsx_souboru>

Příklad:
    python manage.py import_users /path/to/users.xlsx
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.models import User, ReferrerProfile
import openpyxl
from pathlib import Path
import unicodedata


class Command(BaseCommand):
    help = 'Import uživatelů z XLSX souboru'

    def remove_diacritics(self, text):
        """Odstraní diakritiku z textu (á → a, č → c, atd.)"""
        if not text:
            return text
        # Normalizace na NFD (rozklad znaků s diakritikou)
        nfd = unicodedata.normalize('NFD', text)
        # Odstranění combining characters (diakritiky)
        return ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')

    def add_arguments(self, parser):
        parser.add_argument('xlsx_file', type=str, help='Cesta k XLSX souboru s uživateli')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Spustí import bez uložení do databáze (testovací režim)',
        )

    def handle(self, *args, **options):
        xlsx_path = options['xlsx_file']
        dry_run = options['dry_run']

        # Kontrola existence souboru
        if not Path(xlsx_path).exists():
            raise CommandError(f'Soubor {xlsx_path} neexistuje!')

        self.stdout.write(self.style.WARNING(f'Načítám soubor: {xlsx_path}'))

        if dry_run:
            self.stdout.write(self.style.WARNING('REŽIM DRY-RUN: Žádná data nebudou uložena!'))

        # Načtení XLSX souboru
        try:
            workbook = openpyxl.load_workbook(xlsx_path)
            sheet = workbook.active
        except Exception as e:
            raise CommandError(f'Nepodařilo se načíst XLSX soubor: {e}')

        # Načtení hlavičky
        header = [cell.value for cell in sheet[1]]
        self.stdout.write(f'Hlavička: {header}')

        # Mapping sloupců (case-insensitive, s podporou variant)
        header_lower = [h.lower().strip() if h else '' for h in header]
        col_mapping = {}

        # Definice možných variant názvů sloupců
        column_variants = {
            'name': ['jméno', 'name', 'celé jméno'],
            'firstname': ['firstname', 'křestní jméno', 'jmeno'],
            'lastname': ['lastname', 'příjmení', 'prijmeni'],
            'phone': ['mobil', 'phone', 'telefon'],
            'email': ['e-mail pracovní', 'e-mail', 'email'],
            'role': ['uživatelská role', 'role'],
            'manager': ['manažer', 'manager'],
            'commission_referrer': ['provize makléř', 'provize maklér', 'provize makler'],
            'commission_manager': ['provize manažer', 'provize manazer'],
            'commission_office': ['provize kancelář', 'provize kancelar'],
        }

        # Hledání sloupců podle variant
        for key, variants in column_variants.items():
            found = False
            for variant in variants:
                if variant in header_lower:
                    col_mapping[key] = header_lower.index(variant)
                    found = True
                    self.stdout.write(f'  Sloupec "{key}" → "{header[col_mapping[key]]}"')
                    break
            # name, firstname, lastname jsou volitelné - alespoň jedna varianta musí existovat
            if not found and key not in ['name', 'firstname', 'lastname']:
                raise CommandError(f'Sloupec "{key}" nebyl nalezen! Podporované varianty: {variants}')

        # Kontrola, jestli máme buď "name" nebo "firstname" + "lastname"
        has_name = 'name' in col_mapping
        has_firstname_lastname = 'firstname' in col_mapping and 'lastname' in col_mapping

        if not has_name and not has_firstname_lastname:
            raise CommandError('Chybí sloupec se jménem! Očekáván buď "Jméno" nebo "firstname" + "lastname"')

        users_data = []

        # Načtení dat z řádků (přeskočíme hlavičku)
        for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not any(row):  # Přeskočit prázdné řádky
                continue

            try:
                # Zpracování jména - buď z jednoho sloupce "Jméno" nebo z "firstname" + "lastname"
                if has_name:
                    # Formát: jeden sloupec "Jméno" - rozdělíme ho
                    full_name = row[col_mapping['name']]
                    if not full_name or not str(full_name).strip():
                        self.stdout.write(
                            self.style.WARNING(f'Řádek {row_num}: Chybí jméno, přeskakuji')
                        )
                        continue

                    # Rozdělení celého jména na části
                    name_parts = str(full_name).strip().split()
                    if len(name_parts) < 2:
                        self.stdout.write(
                            self.style.WARNING(f'Řádek {row_num}: Neplatné jméno "{full_name}", přeskakuji')
                        )
                        continue

                    firstname = name_parts[0]
                    lastname = ' '.join(name_parts[1:])  # Zbytek jako příjmení
                else:
                    # Formát: oddělené sloupce "firstname" a "lastname"
                    firstname = row[col_mapping['firstname']]
                    lastname = row[col_mapping['lastname']]

                    if not firstname or not lastname:
                        self.stdout.write(
                            self.style.WARNING(f'Řádek {row_num}: Chybí jméno nebo příjmení, přeskakuji')
                        )
                        continue

                    firstname = str(firstname).strip()
                    lastname = str(lastname).strip()

                phone = row[col_mapping['phone']]
                email = row[col_mapping['email']]
                role_str = row[col_mapping['role']]
                manager_name = row[col_mapping['manager']]
                commission_referrer = row[col_mapping['commission_referrer']]
                commission_manager = row[col_mapping['commission_manager']]
                commission_office = row[col_mapping['commission_office']]

                # Použití emailu jako username
                if email and str(email).strip():
                    username = str(email).strip()
                else:
                    # Fallback: generovat z jména (bez diakritiky)
                    firstname_clean = self.remove_diacritics(firstname.lower())
                    lastname_clean = self.remove_diacritics(lastname.lower()).replace(' ', '')
                    username = f"{firstname_clean}{lastname_clean}@housevip.cz"
                    self.stdout.write(
                        self.style.WARNING(f'Řádek {row_num}: Chybí email, generuji username: {username}')
                    )

                # Mapping rolí
                role_mapping = {
                    'makléř': User.Role.REFERRER,
                    'maklér': User.Role.REFERRER,  # varianty psaní
                    'makler': User.Role.REFERRER,
                    'manažer': User.Role.REFERRER_MANAGER,
                    'manazer': User.Role.REFERRER_MANAGER,
                    'manager': User.Role.REFERRER_MANAGER,
                    'kancelář': User.Role.OFFICE,
                    'kancelar': User.Role.OFFICE,
                    'office': User.Role.OFFICE,
                }

                role_str_lower = role_str.lower().strip() if role_str else ''
                role = role_mapping.get(role_str_lower)

                if not role:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Řádek {row_num}: Neznámá role "{role_str}", přeskakuji'
                        )
                    )
                    continue

                # Převod provizí na čísla
                try:
                    commission_referrer = float(commission_referrer or 0)
                    commission_manager = float(commission_manager or 0)
                    commission_office = float(commission_office or 0)
                except (ValueError, TypeError):
                    self.stdout.write(
                        self.style.WARNING(
                            f'Řádek {row_num}: Neplatné hodnoty provizí, nastavuji na 0'
                        )
                    )
                    commission_referrer = commission_manager = commission_office = 0

                users_data.append({
                    'firstname': firstname.strip(),
                    'lastname': lastname.strip(),
                    'username': username,
                    'email': email.strip() if email else username,
                    'phone': str(phone).strip() if phone else '',
                    'role': role,
                    'manager_name': manager_name.strip() if manager_name else None,
                    'commission_referrer': commission_referrer,
                    'commission_manager': commission_manager,
                    'commission_office': commission_office,
                })

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Řádek {row_num}: Chyba při zpracování: {e}')
                )
                continue

        self.stdout.write(self.style.SUCCESS(f'Načteno {len(users_data)} uživatelů ze souboru'))

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN: Zobrazuji prvních 5 uživatelů:'))
            for user_data in users_data[:5]:
                self.stdout.write(f"  - {user_data['firstname']} {user_data['lastname']} ({user_data['username']}) - {user_data['role']}")
            self.stdout.write(self.style.SUCCESS('DRY-RUN dokončen, žádná data nebyla uložena'))
            return

        # Import do databáze (v transakci)
        try:
            with transaction.atomic():
                created_count = 0
                updated_count = 0
                error_count = 0

                # První průchod: Vytvoření všech uživatelů
                self.stdout.write('První průchod: Vytváření uživatelů...')
                for user_data in users_data:
                    try:
                        user, created = User.objects.update_or_create(
                            username=user_data['username'],
                            defaults={
                                'first_name': user_data['firstname'],
                                'last_name': user_data['lastname'],
                                'email': user_data['email'],
                                'phone': user_data['phone'],
                                'role': user_data['role'],
                                'commission_total_per_million': 7000,  # Defaultní hodnota
                                'commission_referrer_pct': user_data['commission_referrer'],
                                'commission_manager_pct': user_data['commission_manager'],
                                'commission_office_pct': user_data['commission_office'],
                            }
                        )

                        # Nastavit heslo pouze pro nové uživatele
                        if created:
                            user.set_password('Hypoteky321')
                            user.save()
                            created_count += 1
                            self.stdout.write(f"  ✓ Vytvořen: {user.get_full_name()} ({user.username})")
                        else:
                            updated_count += 1
                            self.stdout.write(f"  ↻ Aktualizován: {user.get_full_name()} ({user.username})")

                    except Exception as e:
                        error_count += 1
                        self.stdout.write(
                            self.style.ERROR(f"  ✗ Chyba u {user_data['username']}: {e}")
                        )

                # Druhý průchod: Vytvoření ReferrerProfile a propojení manažerů
                self.stdout.write('\nDruhý průchod: Vytváření ReferrerProfile a propojení manažerů...')
                for user_data in users_data:
                    try:
                        user = User.objects.get(username=user_data['username'])

                        # Pro REFERRER, REFERRER_MANAGER a OFFICE vytvoříme ReferrerProfile
                        if user.role in [User.Role.REFERRER, User.Role.REFERRER_MANAGER, User.Role.OFFICE]:
                            # Najít manažera podle jména
                            manager = None
                            if user_data['manager_name']:
                                # Hledáme manažera podle celého jména
                                manager_parts = user_data['manager_name'].split()
                                if len(manager_parts) >= 2:
                                    manager_firstname = manager_parts[0]
                                    manager_lastname = ' '.join(manager_parts[1:])

                                    try:
                                        manager = User.objects.get(
                                            first_name__iexact=manager_firstname,
                                            last_name__iexact=manager_lastname,
                                            role__in=[User.Role.REFERRER_MANAGER, User.Role.OFFICE]
                                        )
                                    except User.DoesNotExist:
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f"  ⚠ Manažer '{user_data['manager_name']}' nenalezen pro {user.username}"
                                            )
                                        )
                                    except User.MultipleObjectsReturned:
                                        self.stdout.write(
                                            self.style.WARNING(
                                                f"  ⚠ Více manažerů se jménem '{user_data['manager_name']}' pro {user.username}"
                                            )
                                        )

                            # Vytvoření nebo aktualizace ReferrerProfile
                            profile, created = ReferrerProfile.objects.update_or_create(
                                user=user,
                                defaults={'manager': manager}
                            )

                            if created:
                                self.stdout.write(f"  ✓ Vytvořen ReferrerProfile pro {user.get_full_name()}")
                            else:
                                self.stdout.write(f"  ↻ Aktualizován ReferrerProfile pro {user.get_full_name()}")

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f"  ✗ Chyba při vytváření profilu pro {user_data['username']}: {e}")
                        )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✓ Import dokončen: {created_count} vytvořeno, {updated_count} aktualizováno, {error_count} chyb'
                    )
                )

        except Exception as e:
            raise CommandError(f'Chyba při importu: {e}')
