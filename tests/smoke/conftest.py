# tests/smoke/conftest.py
# Smoke tests son scripts standalone (corren con python3 directamente, no con pytest).
# Evitar que pytest intente coleccionarlos (tienen imports a nivel módulo con side effects
# que colisionan con el colector de pytest).
collect_ignore_glob = ["test_*"]
