"""
天气服务模块 - 通过IP定位获取当前天气
使用 Open-Meteo API（免费、无需注册）
"""

import requests

# IP定位服务
IP_API_URL = "http://ip-api.com/json/"

# Open-Meteo天气API
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO Weather Code 到中文描述和emoji的映射
WEATHER_CODE_MAP = {
    0: ("晴", "☀️"),
    1: ("大部晴朗", "🌤️"),
    2: ("局部多云", "⛅"),
    3: ("多云", "☁️"),
    45: ("雾", "🌫️"),
    48: ("雾凇", "🌫️"),
    51: ("小毛毛雨", "🌦️"),
    53: ("中毛毛雨", "🌦️"),
    55: ("大毛毛雨", "🌧️"),
    56: ("冻毛毛雨", "🌧️"),
    57: ("冻毛毛雨", "🌧️"),
    61: ("小雨", "🌧️"),
    63: ("中雨", "🌧️"),
    65: ("大雨", "🌧️"),
    66: ("冻雨", "🌧️"),
    67: ("冻雨", "🌧️"),
    71: ("小雪", "🌨️"),
    73: ("中雪", "🌨️"),
    75: ("大雪", "❄️"),
    77: ("雪粒", "🌨️"),
    80: ("小阵雨", "🌦️"),
    81: ("中阵雨", "🌧️"),
    82: ("大阵雨", "🌧️"),
    85: ("小阵雪", "🌨️"),
    86: ("大阵雪", "❄️"),
    95: ("雷暴", "⛈️"),
    96: ("雷暴伴小冰雹", "⛈️"),
    99: ("雷暴伴大冰雹", "⛈️"),
}


def get_weather_desc(code):
    """根据WMO weather code获取中文描述"""
    info = WEATHER_CODE_MAP.get(code)
    return info[0] if info else "未知"


def get_weather_emoji(code):
    """根据WMO weather code获取emoji"""
    info = WEATHER_CODE_MAP.get(code)
    return info[1] if info else "🌡️"


def get_location():
    """通过IP定位获取经纬度，返回 (lat, lon, city) 或 None"""
    try:
        resp = requests.get(IP_API_URL, timeout=3)
        data = resp.json()
        if data.get("status") == "success":
            return data["lat"], data["lon"], data.get("city", "")
    except Exception:
        pass
    return None


def get_current_weather(latitude, longitude):
    """调用 Open-Meteo API 获取当前天气，返回 dict 或 None"""
    try:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,weather_code",
            "timezone": "auto",
        }
        resp = requests.get(OPEN_METEO_URL, params=params, timeout=5)
        data = resp.json()
        current = data.get("current", {})
        code = current.get("weather_code", -1)
        return {
            "temperature": current.get("temperature_2m"),
            "weather_code": code,
            "weather_desc": get_weather_desc(code),
            "weather_emoji": get_weather_emoji(code),
        }
    except Exception:
        return None


def get_weather_auto():
    """一站式获取：IP定位 + 天气，返回 dict 或 None"""
    location = get_location()
    if not location:
        return None
    lat, lon, city = location
    weather = get_current_weather(lat, lon)
    if weather:
        weather["city"] = city
    return weather
