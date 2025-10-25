from django.apps import AppConfig


class MovieRouletteConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'roulette'

    def ready(self):
        import roulette.signals # Import your signals file here