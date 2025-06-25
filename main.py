from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PV_POWER = 2.5
PV_EFFICIENCY = 0.2

def get_url(lat, lon):
	url_base = "https://api.open-meteo.com/v1/forecast?"
	params = [f"latitude={lat}",
		f"longitude={lon}",
		"daily="
	]

	daily_params = [
		"weather_code",
		"temperature_2m_max",
		"temperature_2m_min",
		"sunshine_duration",
		"surface_pressure_mean"
	]

	return(url_base + "&".join(params) + ",".join(daily_params))

def get_forecast_data(lat, lon):
	url = get_url(lat, lon)
	response = requests.get(url)
	return response.json()


@app.get("/forecast/daily")
def get_forecast(lat: float = Query(...), lon: float = Query(...)):
    if not is_valid_geolocation(lat, lon):
        raise HTTPException(status_code=400)
    
    forecast_data = get_forecast_data(lat, lon)
    energy = get_pv_energy(forecast_data["daily"]["sunshine_duration"])
    forecast_data["daily"]["energy"] = energy
    forecast_data["daily_units"]["energy"] = "kWh"
    
    return forecast_data

@app.get("/forecast/summary")
def get_summary(lat: float = Query(...), lon: float = Query(...)):
    if not is_valid_geolocation(lat, lon):
        raise HTTPException(status_code=400)
    
    forecast_data = get_forecast_data(lat, lon)
    forecast_data["weather_summary"] = is_rainy_week(forecast_data["daily"]["weather_code"])
    forecast_data["temperature_min"] = min(forecast_data["daily"]["temperature_2m_min"])
    forecast_data["temperature_max"] = max(forecast_data["daily"]["temperature_2m_max"])
    forecast_data["avg_surface_pressure"] = round(sum(forecast_data["daily"]["surface_pressure_mean"])/7, 2)
    forecast_data["avg_sunshine_duration"] = round(sum(forecast_data["daily"]["sunshine_duration"])/7/3600, 2)
    
    return forecast_data

def is_valid_geolocation(lat, lon):
	try:
		lat = float(lat)
		lon = float(lon)
	except (ValueError, TypeError):
		return False
	return lat in range(-90, 91) and lon in range(-180, 181)
    
def is_rainy_week(weather_codes):
    i = 0
    for wc in weather_codes:
        if wc >= 51:
            i += 1
    return "z opadami" if i>=4 else "bez opadów"

def get_pv_energy(sunshine_array):
    pv_energy = []
    for sd in sunshine_array:
        pv_energy.append(PV_EFFICIENCY * PV_POWER * sd/3600)
    return pv_energy