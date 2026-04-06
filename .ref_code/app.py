"""
Route Optimizer Application

This Flask application optimizes routes between multiple locations using the
nearest neighbor algorithm and displays the optimized route on Google Maps.
"""

import os
import logging
import requests
from flask import Flask, render_template, request
from geopy.distance import geodesic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask application
app = Flask(__name__)

# Configuration
MAPBOX_ACCESS_TOKEN = os.getenv('MAPBOX_ACCESS_TOKEN')
GEOCODING_URL = 'https://api.mapbox.com/geocoding/v5/mapbox.places/'

# Set up logging
log_level = logging.DEBUG
app.logger.setLevel(log_level)

# Create log directory if it doesn't exist
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# Configure file logger
log_file = os.path.join(log_dir, 'app.log')
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(log_level)
file_handler.setFormatter(logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s'))
app.logger.addHandler(file_handler)

# Warn if API token is missing
if not MAPBOX_ACCESS_TOKEN:
    app.logger.warning("MAPBOX_ACCESS_TOKEN environment variable is not set.")


class RouteOptimizer:
    """Handles the route optimization logic using the nearest neighbor algorithm."""
    
    @staticmethod
    def get_coordinates(location):
        """
        Convert a location string to geographic coordinates using Mapbox API.
        
        Args:
            location (str): The address or location name to geocode
            
        Returns:
            tuple: (latitude, longitude) if successful, None otherwise
        """
        app.logger.debug(f"Fetching coordinates for location: {location}")
        params = {
            'access_token': MAPBOX_ACCESS_TOKEN,
            'limit': 1  # Only return the best match
        }

        # Make request to Mapbox API
        response = requests.get(f"{GEOCODING_URL}{location}.json", params=params)
        data = response.json()

        # Extract coordinates from response
        if response.status_code == 200 and 'features' in data and data['features']:
            coords = data['features'][0].get('geometry', {}).get('coordinates', [])
            if coords:
                # Convert from [longitude, latitude] to (latitude, longitude)
                return coords[1], coords[0]
        
        app.logger.error(f"Could not find coordinates for '{location}'")
        return None

    @staticmethod
    def calculate_distance(coord1, coord2):
        """
        Calculate the distance between two geographic coordinates.
        
        Args:
            coord1 (tuple): (latitude, longitude) of the first point
            coord2 (tuple): (latitude, longitude) of the second point
            
        Returns:
            float: Distance in kilometers between the two points
        """
        return geodesic(coord1, coord2).kilometers

    @classmethod
    def optimize_route(cls, locations):
        """
        Optimize a route using the nearest neighbor algorithm.
        
        Args:
            locations (list): List of dictionaries with 'name' and 'coords' keys
            
        Returns:
            list: Ordered list of locations representing the optimized route
        """
        if not locations:
            return []

        app.logger.debug("Optimizing route using nearest neighbor algorithm")
        
        # Start with the first location
        optimized_route = [locations[0]]
        remaining_locations = locations[1:]

        # Find next closest location until all are visited
        while remaining_locations:
            current_location = optimized_route[-1]
            
            # Calculate distances to all remaining locations
            distances = [(cls.calculate_distance(current_location['coords'], loc['coords']), i)
                        for i, loc in enumerate(remaining_locations)]
            
            # Get the nearest location
            nearest_index = min(distances, key=lambda x: x[0])[1]
            
            # Add to route and remove from remaining locations
            optimized_route.append(remaining_locations[nearest_index])
            remaining_locations.pop(nearest_index)

        app.logger.debug(f"Route optimized with {len(optimized_route)} locations")
        return optimized_route


@app.route('/', methods=['GET', 'POST'])
def index():
    """Handle GET and POST requests for the route optimizer."""
    if request.method == 'POST':
        return process_route_request(request.form)
    return render_template('index.html')


def process_route_request(form_data):
    """
    Process form data and generate the optimized route.
    
    Args:
        form_data: Form data from the HTTP request
        
    Returns:
        Rendered template with route data or error message
    """
    app.logger.debug(f"Processing route request")
    has_fixed_destination = 'useFixedDestination' in form_data
    
    # Process locations
    locations = []
    fixed_destination = None
    
    # Process starting point
    start_loc = form_data.get('location_1', '').strip()
    if start_loc:
        start_coords = RouteOptimizer.get_coordinates(start_loc)
        if not start_coords:
            return render_template('index.html', 
                                  error=f"Could not find coordinates for starting point: '{start_loc}'")
        locations.append({'name': start_loc, 'coords': start_coords})
    
    # Process stops
    stop_index = 2
    while form_data.get(f'location_{stop_index}'):
        loc_value = form_data.get(f'location_{stop_index}', '').strip()
        coords = RouteOptimizer.get_coordinates(loc_value)
        if not coords:
            return render_template('index.html', 
                                  error=f"Could not find coordinates for stop: '{loc_value}'")
        locations.append({'name': loc_value, 'coords': coords})
        stop_index += 1
    
    # Process fixed destination if specified
    if has_fixed_destination and form_data.get('fixed_destination'):
        dest_loc = form_data.get('fixed_destination', '').strip()
        dest_coords = RouteOptimizer.get_coordinates(dest_loc)
        if not dest_coords:
            return render_template('index.html', 
                                  error=f"Could not find coordinates for destination: '{dest_loc}'")
        fixed_destination = {'name': dest_loc, 'coords': dest_coords}
    
    # Validate we have enough locations
    if len(locations) < 2:
        return render_template('index.html', error="Please enter at least a starting point and one stop.")
    
    # Optimize the route
    optimized_route = RouteOptimizer.optimize_route(locations)
    
    # Add fixed destination if specified
    if fixed_destination:
        # Remove fixed destination if it's already in the route
        optimized_route = [loc for loc in optimized_route if loc['name'] != fixed_destination['name']]
        optimized_route.append(fixed_destination)
    
    # Generate Google Maps URL
    if optimized_route:
        origin = optimized_route[0]['name']
        destination = optimized_route[-1]['name']
        waypoints = "|".join([loc['name'] for loc in optimized_route[1:-1]]) if len(optimized_route) > 2 else ""
        
        # Create properly encoded URL
        origin_encoded = requests.utils.quote(origin)
        destination_encoded = requests.utils.quote(destination)
        google_maps_url = f"https://www.google.com/maps/dir/?api=1&origin={origin_encoded}&destination={destination_encoded}"
        
        if waypoints:
            waypoints_encoded = requests.utils.quote(waypoints)
            google_maps_url += f"&waypoints={waypoints_encoded}"
        
        return render_template('route.html',
                              origin=origin,
                              destination=destination,
                              waypoints=waypoints,
                              google_maps_url=google_maps_url,
                              locations=optimized_route,
                              has_fixed_destination=has_fixed_destination)
    
    return render_template('index.html', error="Error optimizing the route.")


if __name__ == '__main__':
    # Use environment variables with defaults for host and port
    host = os.getenv('FLASK_RUN_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_RUN_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    app.logger.info(f"Starting application on {host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)