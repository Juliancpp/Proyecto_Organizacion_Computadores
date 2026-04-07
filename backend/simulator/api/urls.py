"""
URL routing for the simulator API.

All endpoints live under /api/ and are included from the project-level urls.py.
"""

from django.urls import path

from simulator.api.views import SimulateView, SimulateRISCView, SimulateCISCView

app_name = "simulator"

urlpatterns = [
    # Full simulation (both architectures)
    path("simulate/", SimulateView.as_view(), name="simulate"),

    # Individual architecture endpoints
    path("simulate/risc/", SimulateRISCView.as_view(), name="simulate-risc"),
    path("simulate/cisc/", SimulateCISCView.as_view(), name="simulate-cisc"),
]
