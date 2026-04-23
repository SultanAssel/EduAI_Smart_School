from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
]

if settings.DEBUG:
    from core.views import serve_media
    urlpatterns += [re_path(r'^media/(?P<path>.*)$', serve_media, name='serve_media')]

# ── Кастомные страницы ошибок (работают при DEBUG=False) ──
handler404 = 'core.views.error_404'
handler500 = 'core.views.error_500'
handler403 = 'core.views.error_403'
