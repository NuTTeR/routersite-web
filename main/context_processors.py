# Для создания глобально-видимых переменных в шаблонах
from django.conf import settings

def servers_url(request):
    return {
        'OSRM_SERVER_URL': settings.OSRM_SERVER_URL,
        'MAP_TILES_SERVER_URL': settings.MAP_TILES_SERVER_URL,
        'SEARCH_SERVER_URL': settings.SEARCH_SERVER_URL,
    }