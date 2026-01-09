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


class Command(BaseCommand):
    help = 'Import uživatelů z XLSX souboru'

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

        # Očekávané sloupce
        expected_columns = [
            'firstname', 'lastname', 'Mobil', 'E-mail',
            'Uživatelská role', 'Manažer',
            'provize makléř', 'provize manažer', 'provize kancelář'
        ]

        # Načtení hlavičky
        header = [cell.value for cell in sheet[1]]
        self.stdout.write(f'Hlavička: {header}')

        # Mapping sloupců (case-insensitive)
        header_lower = [h.lower() if h else '' for h in header]
        col_mapping = {}

        for expected in expected_columns:
            try:
                col_mapping[expected] = header_lower.index(expected.lower())
            except ValueError:
                raise CommandError(f'Sloupec "{expected}" nebyl nalezen v souboru!')

        users_data = []

        # Načtení dat z řádků (přeskočíme hlavičku)
        for row_num, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not any(row):  # Přeskočit prázdné řádky
                continue

            try:
                firstname = row[col_mapping['firstname']]
                lastname = row[col_mapping['lastname']]
                phone = row[col_mapping['Mobil']]
                email = row[col_mapping['E-mail']]
                role_str = row[col_mapping['Uživatelská role']]
                manager_name = row[col_mapping['Manažer']]
                commission_referrer = row[col_mapping['provize makléř']]
                commission_manager = row[col_mapping['provize manažer']]
                commission_office = row[col_mapping['provize kancelář']]

                # Validace povinných polí
                if not firstname or not lastname:
                    self.stdout.write(
                        self.style.WARNING(f'Řádek {row_num}: Chybí jméno nebo příjmení, přeskakuji')
                    )
                    continue

                # Vytvoření username
                username = f"{firstname.lower()}{lastname.lower()}@housevip.cz"

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
