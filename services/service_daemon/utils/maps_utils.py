#!/usr/bin/python

"""
Google Maps utilities for Alfr3d Daemon.
Uses the Google Maps Directions API for travel time and directions.
"""

import os
import logging
from datetime import timedelta

logger = logging.getLogger("MapsUtils")

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
GAS_PRICE = float(os.environ.get("GAS_PRICE", "3.5"))
MPG = float(os.environ.get("MPG", "25"))


def get_travel_info(origin_lat, origin_lng, destination, event_time):
    """
    Calculate departure time, fuel cost, etc. using Google Maps Directions API.
    Returns: Dict with 'departure', 'fuel_cost', or None.
    """
    if not GOOGLE_MAPS_API_KEY:
        logger.warning("GOOGLE_MAPS_API_KEY not set — using placeholder travel info")
        return {
            "departure": event_time - timedelta(minutes=15),
            "fuel_cost": 5.0,
        }

    try:
        import googlemaps

        gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
        result = gmaps.directions(
            origin=(origin_lat, origin_lng),
            destination=destination,
            mode="driving",
            departure_time=event_time,
            traffic_model="best_guess",
        )
        if not result:
            logger.error("Google Maps returned no routes for destination: %s", destination)
            return None

        leg = result[0]["legs"][0]
        duration_seconds = leg["duration"]["value"]
        distance_km = leg["distance"]["value"] / 1000.0
        distance_miles = distance_km * 0.621371

        departure = event_time - timedelta(seconds=duration_seconds)
        fuel_cost = round((distance_miles / MPG) * GAS_PRICE, 2)

        logger.info(
            "Travel info: %s km, %ss drive, depart at %s, fuel cost $%s",
            round(distance_km, 1),
            duration_seconds,
            departure,
            fuel_cost,
        )
        return {
            "departure": departure,
            "fuel_cost": fuel_cost,
            "distance_km": round(distance_km, 1),
            "duration_seconds": duration_seconds,
        }
    except Exception as e:
        logger.error(f"Google Maps Directions API failed: {e}")
        return None
