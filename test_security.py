#!/usr/bin/env python3
"""
Test script for GraphQL security features
Tests depth limiting, complexity analysis, and timeout protection
"""

import requests
import json
import time

# GraphQL endpoint
GRAPHQL_URL = "http://127.0.0.1:5000/graphql"

def test_query(name: str, query: str, should_fail: bool = False):
    """Test a GraphQL query and report results"""
    print(f"\n🔍 Testing: {name}")
    print(f"Query: {query[:100]}{'...' if len(query) > 100 else ''}")
    
    try:
        response = requests.post(
            GRAPHQL_URL,
            json={"query": query},
            timeout=5
        )
        
        result = response.json()
        
        if "errors" in result:
            print(f"❌ Query failed: {result['errors'][0]['message']}")
            if should_fail:
                print("✅ Expected failure - security protection working!")
            else:
                print("⚠️  Unexpected failure")
        else:
            print(f"✅ Query succeeded - returned {len(str(result))} characters")
            if should_fail:
                print("⚠️  Expected this to fail - security may not be working")
        
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {str(e)}")
        return None

def main():
    print("🛡️  GraphQL Security Feature Testing")
    print("=" * 50)
    
    # Test 1: Simple valid query (should work)
    simple_query = """
    {
        sensors {
            id
            name
        }
    }
    """
    test_query("Simple Query", simple_query, should_fail=False)
    
    # Test 2: Deep nested query (should fail due to depth limiting)
    deep_query = """
    {
        sensors {
            readings {
                sensor {
                    readings {
                        sensor {
                            readings {
                                sensor {
                                    readings {
                                        sensor {
                                            id
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    """
    test_query("Deep Nested Query (should fail)", deep_query, should_fail=True)
    
    # Test 3: Complex query with many fields (should fail due to complexity)
    complex_query = """
    {
        sensors {
            id
            name
            readings {
                id
                reading_time
                sensor {
                    id
                    name
                }
                humidity_reading {
                    humidity_percentage
                }
                temperature_reading {
                    temperature_celsius
                }
                co2_reading {
                    co2_ppm
                }
                location {
                    id
                    name
                }
            }
            current_location {
                id
                name
                current_sensors {
                    id
                    name
                }
            }
            last_reading {
                id
                reading_time
            }
        }
        locations {
            id
            name
            current_sensors {
                id
                name
                readings {
                    id
                    reading_time
                }
            }
        }
        sensor_readings {
            id
            reading_time
            sensor {
                id
                name
            }
            humidity_reading {
                humidity_percentage
            }
            temperature_reading {
                temperature_celsius
            }
            co2_reading {
                co2_ppm
            }
        }
    }
    """
    test_query("High Complexity Query (should fail)", complex_query, should_fail=True)
    
    # Test 4: Filtered query with reasonable complexity (should work)
    filtered_query = """
    {
        filteredSensorReadings(filters: {
            limit: 10
            startDate: "2024-01-01T00:00:00"
            endDate: "2024-12-31T23:59:59"
        }) {
            id
            readingTime
            sensor {
                id
                name
            }
            humidityReading {
                humidityPercentage
            }
        }
    }
    """
    test_query("Filtered Query", filtered_query, should_fail=False)
    
    # Test 5: Rate limiting test (multiple rapid requests)
    print(f"\n🔍 Testing: Rate Limiting (50 rapid requests)")
    print("Sending 50 requests rapidly...")
    
    rate_limit_hit = False
    for i in range(50):
        response = requests.post(
            GRAPHQL_URL,
            json={"query": simple_query},
            timeout=1
        )
        
        if response.status_code == 429:
            print(f"✅ Rate limit hit after {i+1} requests - protection working!")
            rate_limit_hit = True
            break
        elif response.status_code != 200:
            print(f"❌ Unexpected status code: {response.status_code}")
            break
    
    if not rate_limit_hit:
        print("⚠️  Rate limit not hit - may need adjustment for testing")
    
    print("\n" + "=" * 50)
    print("🛡️  Security testing complete!")

if __name__ == "__main__":
    main()