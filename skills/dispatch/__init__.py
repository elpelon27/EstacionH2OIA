"""
============================================================================
Dispatch Package — Submódulos del sistema de despacho
Estación H2O · Maracaibo, Venezuela
============================================================================

Exporta:
- DispatcherSkill (orquestador principal)
- DispatcherTelegramBot (bot operadores)
- RouteEngine (VRP + Haversine + Geofencing)
- GPSTracker (Tasker + Telegram + Geofence)
- BottleTracker (SWAP - botellones loaner)
"""

# Orquestador principal
# Motor de rutas
from skills.dispatch.route_engine import (
    ClientOrder,
    RouteResult,
    VRPResult,
    build_distance_matrix,
    check_operation_perimeter,
    check_zone_membership,
    compute_vrp_route,
    find_nearest_zone,
    haversine,
)

# Bot de Telegram para operadores
from skills.dispatch.telegram_bot import DispatcherTelegramBot, get_dispatcher_bot
from skills.dispatcher_skill import DispatcherSkill, get_dispatcher_skill

# GPS Tracker (se implementa en SPRINT 2.3)
from skills.dispatch.gps_tracker import GPSTracker, get_gps_tracker

# Bottle Tracker SWAP (se implementa en SPRINT 3.1)
# from skills.dispatch.bottle_tracker import BottleTracker

__all__ = [
    # Orquestador
    "DispatcherSkill",
    "get_dispatcher_skill",
    # Bot Telegram
    "DispatcherTelegramBot",
    "get_dispatcher_bot",
    # Route Engine
    "haversine",
    "build_distance_matrix",
    "compute_vrp_route",
    "check_operation_perimeter",
    "find_nearest_zone",
    "check_zone_membership",
    "ClientOrder",
    "RouteResult",
    "VRPResult",
    # GPS Tracker
    "GPSTracker",
    "get_gps_tracker",
    # Bottle Tracker (placeholder)
    # "BottleTracker",
]

# Version
__version__ = "2.4.0"
