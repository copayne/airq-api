"""
Air Quality Condition Assessment

Business logic for determining air quality conditions based on sensor readings.
Provides centralized threshold definitions and condition calculations.
"""

from typing import Optional, Dict, Literal
from app.models import SensorReading as SensorReadingModel

# Type alias for air quality conditions
AirQualityCondition = Literal['good', 'moderate', 'poor']


def celsius_to_fahrenheit(celsius: Optional[float]) -> Optional[float]:
    """Convert Celsius to Fahrenheit."""
    if celsius is None:
        return None
    return (celsius * 9/5) + 32


def get_co2_condition(ppm: Optional[float]) -> AirQualityCondition:
    """
    Determine CO2 air quality condition based on PPM value.

    Thresholds:
    - ≤800 PPM: Good
    - 801-999 PPM: Moderate
    - ≥1000 PPM: Poor

    Args:
        ppm: CO2 parts per million reading

    Returns:
        Air quality condition: 'good', 'moderate', or 'poor'
    """
    if ppm is None:
        return 'good'

    if ppm <= 800:
        return 'good'
    elif ppm < 1000:
        return 'moderate'
    else:
        return 'poor'


def get_temperature_condition(fahrenheit: Optional[float]) -> AirQualityCondition:
    """
    Determine temperature air quality condition based on Fahrenheit value.

    Thresholds:
    - <68°F: Good
    - 68-80°F: Moderate
    - ≥81°F: Poor

    Args:
        fahrenheit: Temperature in Fahrenheit

    Returns:
        Air quality condition: 'good', 'moderate', or 'poor'
    """
    if fahrenheit is None:
        return 'good'

    if fahrenheit < 68:
        return 'good'
    elif fahrenheit < 81:
        return 'moderate'
    else:
        return 'poor'


def get_humidity_condition(percentage: Optional[float]) -> AirQualityCondition:
    """
    Determine humidity air quality condition based on percentage value.

    Thresholds:
    - 30-60%: Good (ideal range)
    - 25-30% or 60-70%: Moderate
    - <25% or ≥70%: Poor

    Args:
        percentage: Relative humidity percentage

    Returns:
        Air quality condition: 'good', 'moderate', or 'poor'
    """
    if percentage is None:
        return 'good'

    # Good range: 30-60%
    if 30 < percentage < 60:
        return 'good'

    # Moderate range: 25-30% or 60-70%
    if (25 < percentage <= 30) or (60 <= percentage < 70):
        return 'moderate'

    # Poor range: <25% or ≥70%
    return 'poor'


def condition_to_score(condition: AirQualityCondition) -> float:
    """
    Convert condition to numeric score for weighted calculation.

    Score mapping:
    - good: 0.0
    - moderate: 50.0
    - poor: 100.0

    Args:
        condition: Air quality condition

    Returns:
        Numeric score (0.0 = best, 100.0 = worst)
    """
    if condition == 'good':
        return 0.0
    elif condition == 'moderate':
        return 50.0
    else:  # poor
        return 100.0


def score_to_condition(score: float) -> AirQualityCondition:
    """
    Convert weighted score back to condition category.

    Thresholds:
    - 0-33.33: Good
    - 33.34-66.66: Moderate
    - 66.67-100: Poor

    Args:
        score: Weighted score (0.0 = best, 100.0 = worst)

    Returns:
        Air quality condition: 'good', 'moderate', or 'poor'
    """
    if score <= 33.33:
        return 'good'
    elif score <= 66.66:
        return 'moderate'
    else:
        return 'poor'


def get_overall_condition(
    co2_condition: AirQualityCondition,
    temp_condition: AirQualityCondition,
    humidity_condition: AirQualityCondition
) -> AirQualityCondition:
    """
    Determine overall air quality condition from individual metric conditions.

    Uses weighted scoring system:
    - CO2: 80% weight (most important)
    - Temperature: 15% weight
    - Humidity: 5% weight

    Each condition is converted to a score (good=0, moderate=50, poor=100),
    weighted, then converted back to a final condition.

    Examples:
    - CO2=good, Temp=good, Humidity=good → Score: 0.0 → Overall: good
    - CO2=moderate, Temp=good, Humidity=good → Score: 40.0 → Overall: moderate
    - CO2=poor, Temp=good, Humidity=good → Score: 80.0 → Overall: poor
    - CO2=good, Temp=moderate, Humidity=moderate → Score: 10.0 → Overall: good
    - CO2=poor, Temp=poor, Humidity=poor → Score: 100.0 → Overall: poor

    Args:
        co2_condition: CO2 condition assessment
        temp_condition: Temperature condition assessment
        humidity_condition: Humidity condition assessment

    Returns:
        Overall air quality condition: 'good', 'moderate', or 'poor'
    """
    # Weights
    CO2_WEIGHT = 0.80
    TEMP_WEIGHT = 0.15
    HUMIDITY_WEIGHT = 0.05

    # Convert conditions to scores
    co2_score = condition_to_score(co2_condition)
    temp_score = condition_to_score(temp_condition)
    humidity_score = condition_to_score(humidity_condition)

    # Calculate weighted average
    weighted_score = (
        (co2_score * CO2_WEIGHT) +
        (temp_score * TEMP_WEIGHT) +
        (humidity_score * HUMIDITY_WEIGHT)
    )

    # Convert back to condition
    return score_to_condition(weighted_score)


def assess_reading(reading: SensorReadingModel) -> Dict[str, any]:
    """
    Assess air quality for a single sensor reading.

    Args:
        reading: SensorReading model instance

    Returns:
        Dictionary containing:
        - overall: Overall condition ('good', 'moderate', 'poor')
        - co2: CO2 condition details
        - temperature: Temperature condition details
        - humidity: Humidity condition details
    """
    # Extract measurement values
    co2_ppm = reading.co2_reading.co2_ppm if reading.co2_reading else None
    temp_celsius = reading.temperature_reading.temperature_celsius if reading.temperature_reading else None
    temp_fahrenheit = celsius_to_fahrenheit(temp_celsius)
    humidity_pct = reading.humidity_reading.humidity_percentage if reading.humidity_reading else None

    # Assess each metric
    co2_cond = get_co2_condition(co2_ppm)
    temp_cond = get_temperature_condition(temp_fahrenheit)
    humidity_cond = get_humidity_condition(humidity_pct)

    # Determine overall condition
    overall_cond = get_overall_condition(co2_cond, temp_cond, humidity_cond)

    return {
        'overall': overall_cond,
        'co2': {'condition': co2_cond, 'value': co2_ppm},
        'temperature': {'condition': temp_cond, 'value': temp_fahrenheit},
        'humidity': {'condition': humidity_cond, 'value': humidity_pct},
    }


def calculate_distribution(readings: list[SensorReadingModel]) -> Dict[str, int]:
    """
    Calculate distribution of air quality conditions across multiple readings.

    Args:
        readings: List of SensorReading model instances

    Returns:
        Dictionary containing counts:
        - good: Number of readings with good conditions
        - moderate: Number of readings with moderate conditions
        - poor: Number of readings with poor conditions
        - total: Total number of readings analyzed
    """
    distribution = {
        'good': 0,
        'moderate': 0,
        'poor': 0,
        'total': len(readings)
    }

    for reading in readings:
        assessment = assess_reading(reading)
        condition = assessment['overall']
        distribution[condition] += 1

    return distribution


def calculate_reading_score(reading: SensorReadingModel) -> float:
    """
    Calculate air quality score for a single reading.

    Returns a score from 0-100 where:
    - 100 = perfect air quality (green)
    - 0 = worst air quality (red)

    Args:
        reading: SensorReading model instance

    Returns:
        Score from 0.0 to 100.0
    """
    # Extract measurement values
    co2_ppm = reading.co2_reading.co2_ppm if reading.co2_reading else None
    temp_celsius = reading.temperature_reading.temperature_celsius if reading.temperature_reading else None
    temp_fahrenheit = celsius_to_fahrenheit(temp_celsius)
    humidity_pct = reading.humidity_reading.humidity_percentage if reading.humidity_reading else None

    # Assess each metric
    co2_cond = get_co2_condition(co2_ppm)
    temp_cond = get_temperature_condition(temp_fahrenheit)
    humidity_cond = get_humidity_condition(humidity_pct)

    # Calculate weighted score (0 = best, 100 = worst internally)
    CO2_WEIGHT = 0.80
    TEMP_WEIGHT = 0.15
    HUMIDITY_WEIGHT = 0.05

    co2_score = condition_to_score(co2_cond)
    temp_score = condition_to_score(temp_cond)
    humidity_score = condition_to_score(humidity_cond)

    weighted_score = (
        (co2_score * CO2_WEIGHT) +
        (temp_score * TEMP_WEIGHT) +
        (humidity_score * HUMIDITY_WEIGHT)
    )

    # Invert so 100 = good, 0 = bad
    return 100.0 - weighted_score


def calculate_daily_scores(readings: list[SensorReadingModel], days: int = 365) -> list[Dict]:
    """
    Calculate daily air quality scores for heatmap visualization.

    Groups readings by date and calculates average score for each day.

    Args:
        readings: List of SensorReading model instances
        days: Number of days to include (default 365)

    Returns:
        List of dictionaries containing:
        - date: ISO date string (YYYY-MM-DD)
        - score: Average air quality score (0-100, 100 = best)
        - readingCount: Number of readings for that day
    """
    from datetime import datetime, timedelta
    from collections import defaultdict

    # Group readings by date
    daily_scores = defaultdict(list)

    for reading in readings:
        date_str = reading.reading_time.strftime('%Y-%m-%d')
        score = calculate_reading_score(reading)
        daily_scores[date_str].append(score)

    # Calculate average score for each day
    result = []
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days - 1)

    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        scores = daily_scores.get(date_str, [])

        if scores:
            avg_score = sum(scores) / len(scores)
            result.append({
                'date': date_str,
                'score': round(avg_score, 1),
                'readingCount': len(scores)
            })
        else:
            # No data for this day
            result.append({
                'date': date_str,
                'score': None,
                'readingCount': 0
            })

        current_date += timedelta(days=1)

    return result
