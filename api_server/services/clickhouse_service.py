"""
ClickHouse Service - Database operations for cyclone data
FIXED: Using argMax for getting latest cyclone positions
"""
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import clickhouse_connect

logger = logging.getLogger(__name__)


class ClickHouseService:
    """Service for ClickHouse database operations"""

    def __init__(self):
        self.host = os.getenv('CLICKHOUSE_HOST', 'localhost')
        # FIXED: Use HTTP port 8123 for clickhouse-connect
        self.port = int(os.getenv('CLICKHOUSE_HTTP_PORT', '8123'))
        # FIXED: Use ClickHouse default user (empty password) unless specified
        self.user = os.getenv('CLICKHOUSE_USER', 'default')
        self.password = os.getenv('CLICKHOUSE_PASSWORD', '')
        self.database = os.getenv('CLICKHOUSE_DATABASE', 'cyclones')

        self.client = None
        self._connect()

    def _connect(self):
        """Establish ClickHouse connection"""
        try:
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.user,
                password=self.password,
                database=self.database
            )
            logger.info(f"Connected to ClickHouse at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to ClickHouse: {e}")
            raise

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            result = self.client.query("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"ClickHouse connection test failed: {e}")
            return False

    def get_active_cyclones(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get currently active cyclones (last 24 hours, latest position for each)"""
        # FIXED: Use argMax to get the latest value for each field grouped by id
        query = """
        SELECT 
            id,
            argMax(name, timestamp) as name,
            argMax(basin, timestamp) as basin,
            argMax(classification, timestamp) as classification,
            argMax(intensity, timestamp) as intensity,
            argMax(latitude, timestamp) as latitude,
            argMax(longitude, timestamp) as longitude,
            argMax(movement_speed, timestamp) as movement_speed,
            argMax(movement_direction, timestamp) as movement_direction,
            argMax(central_pressure, timestamp) as central_pressure,
            argMax(max_sustained_wind, timestamp) as max_sustained_wind,
            max(timestamp) as last_seen,
            argMax(data_source, timestamp) as data_source
        FROM cyclone_positions
        WHERE timestamp >= now() - INTERVAL 24 HOUR
        GROUP BY id
        ORDER BY last_seen DESC
        LIMIT {limit}
        """.format(limit=limit)

        try:
            result = self.client.query(query)

            cyclones = []
            for row in result.result_rows:
                cyclones.append({
                    'id': row[0],
                    'name': row[1],
                    'basin': row[2],
                    'classification': row[3],
                    'intensity': row[4],
                    'latitude': float(row[5]),
                    'longitude': float(row[6]),
                    'movement_speed': float(row[7]),
                    'movement_direction': float(row[8]),
                    'central_pressure': float(row[9]) if row[9] else None,
                    'max_sustained_wind': float(row[10]) if row[10] else None,
                    'timestamp': row[11].isoformat() if hasattr(row[11], 'isoformat') else str(row[11]),
                    'data_source': row[12]
                })

            logger.info(f"Retrieved {len(cyclones)} active cyclones")
            return cyclones

        except Exception as e:
            logger.error(f"Error fetching active cyclones: {e}")
            return []

    def get_cyclone_history(self, storm_id: str, hours: int = 72) -> List[Dict[str, Any]]:
        """Get historical positions for a specific cyclone"""
        try:
            query = """
                SELECT 
                    id, name, basin, classification, intensity,
                    latitude, longitude, movement_speed, movement_direction,
                    central_pressure, max_sustained_wind, timestamp
                FROM cyclone_positions
                WHERE id = {storm_id:String}
                  AND timestamp >= now() - INTERVAL {hours:UInt32} HOUR
                ORDER BY timestamp ASC
            """

            result = self.client.query(
                query,
                parameters={'storm_id': storm_id, 'hours': hours}
            )

            history = []
            for row in result.result_rows:
                history.append({
                    'id': row[0],
                    'name': row[1],
                    'basin': row[2],
                    'classification': row[3],
                    'intensity': row[4],
                    'latitude': float(row[5]),
                    'longitude': float(row[6]),
                    'movement_speed': float(row[7]),
                    'movement_direction': float(row[8]),
                    'central_pressure': float(row[9]) if row[9] else None,
                    'max_sustained_wind': float(row[10]) if row[10] else None,
                    'timestamp': row[11].isoformat()
                })

            return history

        except Exception as e:
            logger.error(f"Error fetching cyclone history: {e}")
            return []

    def get_cyclone_metadata(self, storm_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific cyclone"""
        try:
            query = """
                SELECT 
                    id, name, basin, formation_date, dissipation_date,
                    peak_intensity, peak_wind, min_pressure, total_advisories, is_active
                FROM cyclone_metadata
                WHERE id = {storm_id:String}
                ORDER BY last_updated DESC
                LIMIT 1
            """

            result = self.client.query(query, parameters={'storm_id': storm_id})

            if not result.result_rows:
                return None

            row = result.result_rows[0]
            return {
                'id': row[0],
                'name': row[1],
                'basin': row[2],
                'formation_date': row[3].isoformat() if row[3] else None,
                'dissipation_date': row[4].isoformat() if row[4] else None,
                'peak_intensity': row[5],
                'peak_wind': float(row[6]) if row[6] else None,
                'min_pressure': float(row[7]) if row[7] else None,
                'total_advisories': int(row[8]),
                'is_active': bool(row[9])
            }

        except Exception as e:
            logger.error(f"Error fetching cyclone metadata: {e}")
            return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get real-time statistics"""
        try:
            # Count active cyclones (last 24 hours)
            active_query = """
                SELECT uniq(id) as active_count
                FROM cyclone_positions
                WHERE timestamp >= now() - INTERVAL 24 HOUR
            """
            active_result = self.client.query(active_query)
            active_count = active_result.result_rows[0][0]

            # Total observations in last 24 hours
            obs_query = """
                SELECT count() as total_obs
                FROM cyclone_positions
                WHERE timestamp >= now() - INTERVAL 24 HOUR
            """
            obs_result = self.client.query(obs_query)
            total_obs = obs_result.result_rows[0][0]

            # By basin statistics
            basin_query = """
                SELECT 
                    basin,
                    uniq(id) as storm_count,
                    avg(max_sustained_wind) as avg_wind,
                    max(max_sustained_wind) as max_wind
                FROM cyclone_positions
                WHERE timestamp >= now() - INTERVAL 24 HOUR
                GROUP BY basin
            """
            basin_result = self.client.query(basin_query)

            basins = {}
            for row in basin_result.result_rows:
                basins[row[0]] = {
                    'storm_count': int(row[1]),
                    'avg_wind': float(row[2]) if row[2] else 0,
                    'max_wind': float(row[3]) if row[3] else 0
                }

            return {
                'total_active': active_count,
                'total_observations_24h': total_obs,
                'basins': basins,
                'last_update': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error fetching statistics: {e}")
            return {
                'total_active': 0,
                'total_observations_24h': 0,
                'basins': {},
                'last_update': datetime.utcnow().isoformat()
            }

    def get_forecast_data(self, storm_id: str, hours_back: int = 24) -> List[Dict[str, Any]]:
        """Get official forecast data if available"""
        try:
            query = """
                SELECT 
                    id, name, forecast_hour, forecast_timestamp,
                    latitude, longitude, max_wind, min_pressure,
                    forecast_type, issued_at
                FROM cyclone_forecasts
                WHERE id = {storm_id:String}
                  AND issued_at >= now() - INTERVAL {hours:UInt32} HOUR
                ORDER BY issued_at DESC, forecast_hour ASC
            """

            result = self.client.query(
                query,
                parameters={'storm_id': storm_id, 'hours': hours_back}
            )

            forecasts = []
            for row in result.result_rows:
                forecasts.append({
                    'id': row[0],
                    'name': row[1],
                    'forecast_hour': int(row[2]),
                    'forecast_timestamp': row[3].isoformat(),
                    'latitude': float(row[4]),
                    'longitude': float(row[5]),
                    'max_wind': float(row[6]) if row[6] else None,
                    'min_pressure': float(row[7]) if row[7] else None,
                    'forecast_type': row[8],
                    'issued_at': row[9].isoformat()
                })

            return forecasts

        except Exception as e:
            logger.error(f"Error fetching forecast data: {e}")
            return []

    def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()