"""Gazetteer views."""


from django.shortcuts import render


def gazetteer_map(request):
    """Render a Leaflet map of all current gazetteer locations."""
    return render(request, "gazetteer/map.html")
