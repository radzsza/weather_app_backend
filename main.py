from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://weather-app-frontend-gd25.onrender.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# stałe do obliczania energii wydzielanej przez panele
PV_POWER = 2.5 # moc panelu [kWh]
PV_EFFICIENCY = 0.2 # wydajność panelu

# endpoint czysto dla deployu na render.com - bez niego nie ma root page
@app.get("/")
def read_root():
    return {"status": "ok"}

# zwraca URL do openmeteo API z parametrami potrzebnymi do wyświetlenia
def get_url(lat, lon) -> str:
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
	return(url_base + "&".join(params) + ",".join(daily_params) + "&timezone=auto")

# obsługa błędów API - zwrócenie odpowiedniego HTTPException
# jeśli nie pojawia się błąd, zwraca dane w formacie json
def get_forecast_data(lat, lon) -> dict:
	url = get_url(lat, lon)
	try:
		response = requests.get(url, timeout=5)
		response.raise_for_status()
	except requests.exceptions.Timeout:
		raise HTTPException(status_code=504, detail="API pogodowe nie odpowiada (timeout)")
	except requests.exceptions.RequestException as e:
		raise HTTPException(status_code=502, detail=f"Błąd połączenia z API: {e}")

	try:
		data = response.json()
	except ValueError:
		raise HTTPException(status_code=500, detail="Nieprawidłowy format danych z API")

	if "daily" not in data:
		raise HTTPException(status_code=500, detail="Brak danych pogodowych w odpowiedzi API")

	return data

# zwraca dane pogodowe z dodanymi wartościami energii wygenerowanej przez panele pv
@app.get("/forecast/daily")
def get_forecast(lat: float = Query(...), lon: float = Query(...)) -> dict:
    if not is_valid_geolocation(lat, lon):
        raise HTTPException(status_code=400, detail="Niepoprawne dane, nie można pobrać prognozy")
    
    forecast_data = get_forecast_data(lat, lon)
    energy = get_pv_energy(forecast_data["daily"]["sunshine_duration"])
    forecast_data["daily"]["energy"] = energy
    forecast_data["daily_units"]["energy"] = "kWh"
    
    return forecast_data

# zwraca podstawowe dane pogodowe + średnie/skrajne wartości do podsumowania
@app.get("/forecast/summary")
def get_summary(lat: float = Query(...), lon: float = Query(...)) -> dict:
    if not is_valid_geolocation(lat, lon):
        raise HTTPException(status_code=400, detail="Niepoprawne dane, nie można pobrać podsumowania")
    
    forecast_data = get_forecast_data(lat, lon)
    forecast_data["weather_summary"] = is_rainy_week(forecast_data["daily"]["weather_code"])
    forecast_data["temperature_min"] = min(forecast_data["daily"]["temperature_2m_min"])
    forecast_data["temperature_max"] = max(forecast_data["daily"]["temperature_2m_max"])
    forecast_data["avg_surface_pressure"] = round(sum(forecast_data["daily"]["surface_pressure_mean"])/7, 2)
    forecast_data["avg_sunshine_duration"] = round(sum(forecast_data["daily"]["sunshine_duration"])/7/3600, 2)
    
    return forecast_data

# walidacja danych - kontrola typu (czy jest liczbą) i poprawności zakresu 
def is_valid_geolocation(lat, lon) -> bool:
	try:
		lat = float(lat)
		lon = float(lon)
	except (ValueError, TypeError):
		return False
	return -90 <= lat <= 90 and -180 <= lon <= 180

# podsumowanie tygodnia (opadów) - jeśli >= 4 dni z opadami, to tydzień ma status "z opadami"
def is_rainy_week(weather_codes) -> str:
    rainy_days = sum(wc >= 51 for wc in weather_codes)
    return "z opadami" if rainy_days >= 4 else "bez opadów"

# obliczanie energii generowanej przez panele pv dla każdego dnia
# zwraca listę wartości
def get_pv_energy(sunshine_array: list[float]) -> list[float]:
    return [PV_EFFICIENCY * PV_POWER * sd / 3600 for sd in sunshine_array]