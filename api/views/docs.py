from django.shortcuts import render


def api_docs(request):
    """Human-readable reference for the API surface."""
    return render(request, "api/docs.html")