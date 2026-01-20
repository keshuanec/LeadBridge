from django.apps import AppConfig


class LeadsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'leads'

    def ready(self):
        """Import signals and middleware when the app is ready"""
        import leads.signals  # noqa
        import leads.middleware  # noqa
