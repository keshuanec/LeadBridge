from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from accounts.models import ReferrerProfile, Office, ManagerProfile
from leads.models import Lead, Deal
from leads.forms import LeadForm

User = get_user_model()


class AdvisorAccessTestCase(TestCase):
    """
    Test suite pro admin access funkce poradců (ADVISOR) s ReferrerProfile.

    Testované požadavky:
    1. Advisor vidí leady kde je přiřazen jako advisor
    2. Advisor vidí leady kde referrer má advisora v seznamu advisors
    3. Advisor vidí dealy podle stejné logiky
    4. Advisor může přidělovat leady svým podřízeným referrerům
    5. Advisor s ReferrerProfile může vytvořit lead za sebe jako referrer
    """

    def setUp(self):
        """Příprava testovacích dat"""

        # Vytvořit uživatele
        self.advisor = User.objects.create_user(
            username="advisor1",
            password="test123",
            role=User.Role.ADVISOR,
            first_name="Test",
            last_name="Advisor",
            commission_total_per_million=7000,
            commission_referrer_pct=50,
            commission_manager_pct=10,
            commission_office_pct=40,
        )

        self.advisor_with_profile = User.objects.create_user(
            username="advisor_ref",
            password="test123",
            role=User.Role.ADVISOR,
            first_name="Advisor",
            last_name="WithProfile",
            commission_total_per_million=7000,
            commission_referrer_pct=50,
            commission_manager_pct=10,
            commission_office_pct=40,
        )

        self.referrer1 = User.objects.create_user(
            username="referrer1",
            password="test123",
            role=User.Role.REFERRER,
            first_name="Referrer",
            last_name="One",
            commission_total_per_million=7000,
            commission_referrer_pct=90,
            commission_manager_pct=10,
            commission_office_pct=0,
        )

        self.referrer2 = User.objects.create_user(
            username="referrer2",
            password="test123",
            role=User.Role.REFERRER,
            first_name="Referrer",
            last_name="Two",
            commission_total_per_million=7000,
            commission_referrer_pct=90,
            commission_manager_pct=10,
            commission_office_pct=0,
        )

        self.referrer3 = User.objects.create_user(
            username="referrer3",
            password="test123",
            role=User.Role.REFERRER,
            first_name="Referrer",
            last_name="Three",
            commission_total_per_million=7000,
            commission_referrer_pct=90,
            commission_manager_pct=10,
            commission_office_pct=0,
        )

        self.other_advisor = User.objects.create_user(
            username="advisor2",
            password="test123",
            role=User.Role.ADVISOR,
            first_name="Other",
            last_name="Advisor",
        )

        # Vytvořit ReferrerProfile pro referrery a přiřadit advisora
        self.ref1_profile = ReferrerProfile.objects.create(user=self.referrer1)
        self.ref1_profile.advisors.add(self.advisor)

        self.ref2_profile = ReferrerProfile.objects.create(user=self.referrer2)
        self.ref2_profile.advisors.add(self.advisor)

        self.ref3_profile = ReferrerProfile.objects.create(user=self.referrer3)
        # referrer3 NEMÁ advisora přiřazeného - pro negativní testy

        # Vytvořit ReferrerProfile pro advisora (aby mohl být referrer)
        self.advisor_ref_profile = ReferrerProfile.objects.create(user=self.advisor_with_profile)
        self.advisor_ref_profile.advisors.add(self.advisor)
        self.advisor_ref_profile.advisors.add(self.advisor_with_profile)  # může vybrat i sebe

        # Client pro HTTP requesty
        self.client = Client()

    def test_advisor_sees_own_assigned_leads(self):
        """Test: Advisor vidí leady, kde je přiřazen jako advisor"""

        # Lead kde je advisor přiřazen
        lead1 = Lead.objects.create(
            referrer=self.referrer1,
            advisor=self.advisor,
            client_name="Client 1",
            client_phone="+420123456789",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("my_leads"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(lead1, response.context["leads"])

    def test_advisor_sees_subordinate_referrer_leads(self):
        """Test: Advisor vidí leady referrerů, kteří mají advisora v seznamu advisors"""

        # Lead kde referrer má advisora v seznamu (ale advisor není přiřazen na lead)
        lead2 = Lead.objects.create(
            referrer=self.referrer1,
            advisor=self.other_advisor,  # jiný advisor je přiřazen
            client_name="Client 2",
            client_phone="+420123456790",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("my_leads"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(lead2, response.context["leads"])

    def test_advisor_does_not_see_unrelated_leads(self):
        """Test: Advisor NEVIDÍ leady, kde není přiřazen a referrer ho nemá v seznamu"""

        # Lead kde referrer NEMÁ advisora v seznamu
        lead3 = Lead.objects.create(
            referrer=self.referrer3,
            advisor=self.other_advisor,
            client_name="Client 3",
            client_phone="+420123456791",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("my_leads"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(lead3, response.context["leads"])

    def test_advisor_sees_both_conditions(self):
        """Test: Advisor vidí lead když jsou obě podmínky splněny (assigned + subordinate)"""

        # Lead kde je advisor přiřazen A referrer má advisora v seznamu
        lead4 = Lead.objects.create(
            referrer=self.referrer2,
            advisor=self.advisor,
            client_name="Client 4",
            client_phone="+420123456792",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("my_leads"))

        self.assertEqual(response.status_code, 200)
        # Měl by být jen jednou (díky distinct())
        lead_count = list(response.context["leads"]).count(lead4)
        self.assertEqual(lead_count, 1)

    def test_advisor_can_access_subordinate_lead_detail(self):
        """Test: Advisor může zobrazit detail leadu svého podřízeného referrera"""

        lead = Lead.objects.create(
            referrer=self.referrer1,
            advisor=self.other_advisor,
            client_name="Client Detail",
            client_phone="+420123456793",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("lead_detail", args=[lead.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["lead"], lead)

    def test_advisor_cannot_access_unrelated_lead_detail(self):
        """Test: Advisor NEMŮŽE zobrazit detail leadu, na který nemá právo"""

        lead = Lead.objects.create(
            referrer=self.referrer3,
            advisor=self.other_advisor,
            client_name="Client No Access",
            client_phone="+420123456794",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("lead_detail", args=[lead.pk]))

        self.assertEqual(response.status_code, 404)

    def test_advisor_sees_subordinate_deals(self):
        """Test: Advisor vidí dealy svých podřízených referrerů"""

        lead = Lead.objects.create(
            referrer=self.referrer1,
            advisor=self.other_advisor,
            client_name="Deal Client",
            client_phone="+420123456795",
            communication_status=Lead.CommunicationStatus.DEAL_CREATED,
        )

        deal = Deal.objects.create(
            lead=lead,
            client_name="Deal Client",
            client_phone="+420123456795",
            loan_amount=2000000,
            bank=Deal.Bank.CS,
            property_type=Deal.PropertyType.OWN,
            status=Deal.DealStatus.REQUEST_IN_BANK,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("deals_list"))

        self.assertEqual(response.status_code, 200)
        deal_ids = [d.pk for d in response.context["deals"]]
        self.assertIn(deal.pk, deal_ids)

    def test_advisor_does_not_see_unrelated_deals(self):
        """Test: Advisor NEVIDÍ dealy, na které nemá právo"""

        lead = Lead.objects.create(
            referrer=self.referrer3,
            advisor=self.other_advisor,
            client_name="Deal Client Unrelated",
            client_phone="+420123456796",
            communication_status=Lead.CommunicationStatus.DEAL_CREATED,
        )

        deal = Deal.objects.create(
            lead=lead,
            client_name="Deal Client Unrelated",
            client_phone="+420123456796",
            loan_amount=2000000,
            bank=Deal.Bank.CS,
            property_type=Deal.PropertyType.OWN,
            status=Deal.DealStatus.REQUEST_IN_BANK,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("deals_list"))

        self.assertEqual(response.status_code, 200)
        deal_ids = [d.pk for d in response.context["deals"]]
        self.assertNotIn(deal.pk, deal_ids)

    def test_advisor_can_access_subordinate_deal_detail(self):
        """Test: Advisor může zobrazit detail dealu svého podřízeného referrera"""

        lead = Lead.objects.create(
            referrer=self.referrer1,
            advisor=self.other_advisor,
            client_name="Deal Detail Client",
            client_phone="+420123456797",
            communication_status=Lead.CommunicationStatus.DEAL_CREATED,
        )

        deal = Deal.objects.create(
            lead=lead,
            client_name="Deal Detail Client",
            client_phone="+420123456797",
            loan_amount=2000000,
            bank=Deal.Bank.CS,
            property_type=Deal.PropertyType.OWN,
            status=Deal.DealStatus.REQUEST_IN_BANK,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("deal_detail", args=[deal.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["deal"], deal)

    def test_advisor_cannot_access_unrelated_deal_detail(self):
        """Test: Advisor NEMŮŽE zobrazit detail dealu, na který nemá právo"""

        lead = Lead.objects.create(
            referrer=self.referrer3,
            advisor=self.other_advisor,
            client_name="Deal No Access Client",
            client_phone="+420123456798",
            communication_status=Lead.CommunicationStatus.DEAL_CREATED,
        )

        deal = Deal.objects.create(
            lead=lead,
            client_name="Deal No Access Client",
            client_phone="+420123456798",
            loan_amount=2000000,
            bank=Deal.Bank.CS,
            property_type=Deal.PropertyType.OWN,
            status=Deal.DealStatus.REQUEST_IN_BANK,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("deal_detail", args=[deal.pk]))

        self.assertEqual(response.status_code, 404)

    def test_advisor_lead_form_shows_correct_referrers(self):
        """Test: LeadForm pro advisora ukazuje správné referrery (podřízené + sebe)"""

        # Advisor БЕЗ ReferrerProfile
        form = LeadForm(user=self.advisor)
        referrer_queryset = form.fields["referrer"].queryset

        # Měl by vidět jen referrer1 a referrer2 (ne referrer3)
        self.assertIn(self.referrer1, referrer_queryset)
        self.assertIn(self.referrer2, referrer_queryset)
        self.assertNotIn(self.referrer3, referrer_queryset)
        self.assertNotIn(self.advisor, referrer_queryset)  # nemá ReferrerProfile

    def test_advisor_with_profile_sees_self_in_referrers(self):
        """Test: Advisor S ReferrerProfile vidí sebe v seznamu referrerů"""

        form = LeadForm(user=self.advisor_with_profile)
        referrer_queryset = form.fields["referrer"].queryset

        # Měl by vidět sebe
        self.assertIn(self.advisor_with_profile, referrer_queryset)

    def test_advisor_can_create_lead_for_subordinate(self):
        """Test: Advisor může vytvořit lead pro podřízeného referrera"""

        self.client.login(username="advisor1", password="test123")

        response = self.client.post(reverse("lead_create"), {
            "client_name": "New Client",
            "client_phone": "+420999888777",
            "client_email": "client@example.com",
            "advisor": self.advisor.pk,
            "referrer": self.referrer1.pk,
            "communication_status": Lead.CommunicationStatus.NEW,
            "description": "Test lead",
        })

        # Měl by vytvořit a přesměrovat
        self.assertEqual(response.status_code, 302)

        # Ověřit, že lead existuje
        lead = Lead.objects.filter(
            client_name="New Client",
            referrer=self.referrer1,
            advisor=self.advisor,
        ).first()

        self.assertIsNotNone(lead)

    def test_advisor_with_profile_can_create_lead_as_referrer(self):
        """Test: Advisor s ReferrerProfile může vytvořit lead za sebe jako referrer"""

        self.client.login(username="advisor_ref", password="test123")

        response = self.client.post(reverse("lead_create"), {
            "client_name": "Self Referral Client",
            "client_phone": "+420888777666",
            "client_email": "self@example.com",
            "advisor": self.advisor_with_profile.pk,
            "referrer": self.advisor_with_profile.pk,  # sám sebe jako referrer
            "communication_status": Lead.CommunicationStatus.NEW,
            "description": "Self referral test",
        })

        # Měl by vytvořit a přesměrovat
        self.assertEqual(response.status_code, 302)

        # Ověřit, že lead existuje
        lead = Lead.objects.filter(
            client_name="Self Referral Client",
            referrer=self.advisor_with_profile,
            advisor=self.advisor_with_profile,
        ).first()

        self.assertIsNotNone(lead)

    def test_advisor_overview_shows_correct_leads(self):
        """Test: Overview pro advisora ukazuje správné leady"""

        lead1 = Lead.objects.create(
            referrer=self.referrer1,
            advisor=self.advisor,
            client_name="Overview Client 1",
            client_phone="+420111222333",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        lead2 = Lead.objects.create(
            referrer=self.referrer2,
            advisor=self.other_advisor,
            client_name="Overview Client 2",
            client_phone="+420111222334",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        lead3 = Lead.objects.create(
            referrer=self.referrer3,
            advisor=self.other_advisor,
            client_name="Overview Client 3",
            client_phone="+420111222335",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("overview"))

        self.assertEqual(response.status_code, 200)

        # lead1 a lead2 by měly být v nových leadech
        new_leads = list(response.context["new_leads"])
        self.assertIn(lead1, new_leads)
        self.assertIn(lead2, new_leads)
        self.assertNotIn(lead3, new_leads)

    def test_advisor_overview_shows_correct_deals(self):
        """Test: Overview pro advisora ukazuje správné dealy"""

        lead1 = Lead.objects.create(
            referrer=self.referrer1,
            advisor=self.advisor,
            client_name="Overview Deal 1",
            client_phone="+420222333444",
            communication_status=Lead.CommunicationStatus.DEAL_CREATED,
        )

        deal1 = Deal.objects.create(
            lead=lead1,
            client_name="Overview Deal 1",
            client_phone="+420222333444",
            loan_amount=3000000,
            bank=Deal.Bank.CS,
            property_type=Deal.PropertyType.OWN,
            status=Deal.DealStatus.REQUEST_IN_BANK,
        )

        lead2 = Lead.objects.create(
            referrer=self.referrer3,
            advisor=self.other_advisor,
            client_name="Overview Deal 2",
            client_phone="+420222333445",
            communication_status=Lead.CommunicationStatus.DEAL_CREATED,
        )

        deal2 = Deal.objects.create(
            lead=lead2,
            client_name="Overview Deal 2",
            client_phone="+420222333445",
            loan_amount=3000000,
            bank=Deal.Bank.CS,
            property_type=Deal.PropertyType.OWN,
            status=Deal.DealStatus.REQUEST_IN_BANK,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("overview"))

        self.assertEqual(response.status_code, 200)

        # deal1 by měl být v dealech, deal2 ne
        deals = list(response.context["deals"])
        deal_ids = [d.pk for d in deals]
        self.assertIn(deal1.pk, deal_ids)
        self.assertNotIn(deal2.pk, deal_ids)

    def test_distinct_prevents_duplicates(self):
        """Test: .distinct() zabraňuje duplikátům když obě podmínky platí"""

        # Lead kde advisor je přiřazen A referrer má advisora v seznamu
        lead = Lead.objects.create(
            referrer=self.referrer1,
            advisor=self.advisor,
            client_name="Duplicate Test",
            client_phone="+420333444555",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        self.client.login(username="advisor1", password="test123")
        response = self.client.get(reverse("my_leads"))

        self.assertEqual(response.status_code, 200)

        # Lead by měl být v seznamu jen jednou
        leads_list = list(response.context["leads"])
        self.assertEqual(leads_list.count(lead), 1)


class AdvisorAccessEdgeCasesTestCase(TestCase):
    """Edge case testy pro advisor access"""

    def setUp(self):
        """Příprava testovacích dat"""

        self.advisor_no_profile = User.objects.create_user(
            username="advisor_no_profile",
            password="test123",
            role=User.Role.ADVISOR,
        )

        self.advisor_empty_list = User.objects.create_user(
            username="advisor_empty",
            password="test123",
            role=User.Role.ADVISOR,
        )

        # Prázdný ReferrerProfile (žádní advisoři přiřazení)
        ReferrerProfile.objects.create(user=self.advisor_empty_list)

        self.referrer = User.objects.create_user(
            username="referrer",
            password="test123",
            role=User.Role.REFERRER,
            commission_total_per_million=7000,
            commission_referrer_pct=100,
            commission_manager_pct=0,
            commission_office_pct=0,
        )

        self.client = Client()

    def test_advisor_without_profile_still_sees_assigned_leads(self):
        """Test: Advisor BEZ ReferrerProfile stále vidí své přiřazené leady"""

        lead = Lead.objects.create(
            referrer=self.referrer,
            advisor=self.advisor_no_profile,
            client_name="Assigned Lead",
            client_phone="+420444555666",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        self.client.login(username="advisor_no_profile", password="test123")
        response = self.client.get(reverse("my_leads"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(lead, response.context["leads"])

    def test_advisor_with_empty_profile_only_sees_assigned(self):
        """Test: Advisor s prázdným ReferrerProfile vidí jen své přiřazené leady"""

        lead1 = Lead.objects.create(
            referrer=self.referrer,
            advisor=self.advisor_empty_list,
            client_name="Assigned to Empty",
            client_phone="+420555666777",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        lead2 = Lead.objects.create(
            referrer=self.referrer,
            advisor=self.advisor_no_profile,
            client_name="Not Assigned",
            client_phone="+420555666778",
            communication_status=Lead.CommunicationStatus.NEW,
        )

        self.client.login(username="advisor_empty", password="test123")
        response = self.client.get(reverse("my_leads"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(lead1, response.context["leads"])
        self.assertNotIn(lead2, response.context["leads"])

    def test_form_with_no_subordinates_shows_empty_queryset(self):
        """Test: LeadForm pro advisora bez podřízených ukazuje prázdný queryset referrerů"""

        form = LeadForm(user=self.advisor_no_profile)
        referrer_queryset = form.fields["referrer"].queryset

        # Měl by být prázdný (nemá žádné podřízené)
        self.assertEqual(referrer_queryset.count(), 0)

    def test_form_with_empty_profile_shows_only_self(self):
        """Test: LeadForm pro advisora s prázdným ReferrerProfile ukazuje jen sebe"""

        form = LeadForm(user=self.advisor_empty_list)
        referrer_queryset = form.fields["referrer"].queryset

        # Měl by vidět jen sebe (má ReferrerProfile)
        self.assertEqual(referrer_queryset.count(), 1)
        self.assertIn(self.advisor_empty_list, referrer_queryset)
