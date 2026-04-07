"""
Root URL configuration for the RISC vs CISC CPU Simulator.

All API routes are namespaced under /api/.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('simulator.api.urls', namespace='simulator')),
]
