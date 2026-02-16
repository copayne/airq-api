# AirQ Backend Cleanup Plan

Comprehensive audit of `/home/copayne/dev/airq/airq-api` identifying dead code, unused database structures, dead GraphQL endpoints, bugs, and simplification opportunities.

---

## 1. BUGS (Fix Immediately)

### 1.1 `sensor_reading.timestamp` does not exist
- **File:** `app/schema.py:345`
- **Issue:** `CreateSensorReading.mutate()` references `sensor_reading.timestamp` in the WebSocket publish payload, but `SensorReading` has no `timestamp` column. The correct attribute is `reading_time`.
- **Impact:** WebSocket `sensor_reading` events send `"None"` as the timestamp string, or raise an `AttributeError` silently caught by the surrounding try/except.
- **Action:** Change `sensor_reading.timestamp` to `sensor_reading.reading_time`.
- **Safe to fix:** Yes, no other dependencies.

### 1.2 `latest_snapshot.device_id` does not exist
- **File:** `app/schema.py:1368`
- **Issue:** `CaptureRingSnapshot.mutate()` logs `latest_snapshot.device_id` in its extra context, but `RingSnapshot` has no `device_id` column. It has `camera_id`.
- **Impact:** Logging silently fails or produces `None`.
- **Action:** Change to `latest_snapshot.camera_id`.
- **Safe to fix:** Yes.

### 1.3 `input.device_id` reference on wrong input type
- **File:** `app/schema.py:1264`
- **Issue:** `CreateRingSnapshot.mutate()` error handler references `input.device_id`, but `CreateRingSnapshotInput` defines `camera_id`, not `device_id`.
- **Impact:** Error logging will raise `AttributeError`, caught by itself.
- **Action:** Change to `input.camera_id`.
- **Safe to fix:** Yes.

---

## 2. UNUSED / DEAD DATABASE TABLES

### 2.1 `Camera` model overlaps with `RingDevice`
- **File:** `app/models.py:542-560` (Camera), `app/models.py:582-602` (RingDevice)
- **Issue:** Both `Camera` and `RingDevice` store Ring device metadata. `Camera` is specifically for cameras with snapshots, while `RingDevice` covers all Ring alarm devices. However, both have `device_id`, `name`, `location`, `model`/`device_type`, `is_active` columns. They serve different purposes (Camera is for snapshots, RingDevice for contact sensors / other devices), but the naming is confusing and they could potentially be unified.
- **Action:** Keep both for now (they serve distinct roles), but consider consolidating in a future refactor with a `device_type` discriminator.
- **Priority:** Low

### 2.2 `ApplicationErrorLog` table - Internal only
- **File:** `app/models.py:522-540`
- **Issue:** This table is only written to by `DatabaseLogHandler` in `app/logging_config.py`. It is never queried in any API endpoint or GraphQL resolver. It exists purely for backend log persistence.
- **Action:** This is working as intended (write-only logging table). No action needed. Could consider adding a GraphQL query for admin log viewing in the future.
- **Priority:** None (not dead, just internal)

---

## 3. UNUSED / ORPHAN MODEL COLUMNS

### 3.1 `Sensor.calibration_port` - used only in schema mutations
- **File:** `app/models.py:326`
- **Analysis:** Used in `CalibrateSensorFRC`, `SetSensorASC`, `SetSensorTemperatureOffset`, `FactoryResetSensor`, `GetSensorCalibrationStatus` mutations. Actively used.
- **Action:** Keep.

### 3.2 `SensorReading.is_success` - never written
- **File:** `app/models.py:471`
- **Issue:** The `is_success` column on `SensorReading` defaults to `True` but is never explicitly set to `False` anywhere. The `Sensor.update_health_on_reading()` method accepts a `success` parameter, but `CreateSensorReading.mutate()` always calls it with `success=True`. There is no code path that creates a reading with `is_success=False`.
- **Action:** Evaluate whether failed readings should set this, or remove the column if it serves no purpose.
- **Priority:** Low

### 3.3 `ErrorLog.request_data` and `ErrorLog.response_data` - never written by API
- **File:** `app/models.py:515-516`
- **Issue:** These fields exist on the `ErrorLog` model but are never populated by the `CreateSensorReading` mutation or any other code path. The `ErrorLog` relationship exists on `SensorReading` but no code ever creates `ErrorLog` records.
- **Action:** If sensor-level error logging is needed, implement it. Otherwise, the entire `ErrorLog` table and its associated GraphQL type/resolver (`ErrorLogObject`, `resolve_error_logs`) could be considered dead code.
- **Priority:** Medium

### 3.4 `ApplicationErrorLog.request_id` and `ApplicationErrorLog.user_id`
- **File:** `app/models.py:530-531`
- **Issue:** `request_id` is populated via `RequestIDFilter`, which works. `user_id` has a comment saying "For future authentication" and is never populated (always `None`). The `DatabaseLogHandler.emit()` uses `getattr(record, 'user_id', None)` which will always be `None` since no code sets it.
- **Action:** Either implement user_id population in the logging handler (e.g., from `g.current_user`) or remove the column.
- **Priority:** Low

---

## 4. DEAD / UNDERUSED GRAPHQL ENDPOINTS

### 4.1 Standalone measurement queries (never used by frontend components)
- **Backend:** `resolve_humidity_readings`, `resolve_temperature_readings`, `resolve_co2_readings` in `app/schema.py:3833-3840`
- **Frontend:** `GET_CO2_READINGS`, `GET_TEMPERATURE_READINGS`, `GET_HUMIDITY_READINGS` defined in `airq-fe/src/graphql/Measurements.ts`
- **Frontend hooks:** `useCO2Measurements`, `useTemperatureMeasurements`, `useHumidityMeasurements` defined in `airq-fe/src/hooks/useMeasurements.ts`
- **Issue:** These hooks are exported from `hooks/index.ts` but **never imported by any component**. All dashboard widgets use `filteredSensorReadings` via `useWidgetSensorData` instead. These are vestigial from an earlier architecture.
- **Action:** Remove from both frontend and backend. The `filteredSensorReadings` query supersedes these.
- **Priority:** Medium
- **Safe to remove:** Yes - no component imports these hooks.

### 4.2 `resolve_sensor_readings` (bulk unfiltered query)
- **Backend:** `app/schema.py:3821-3831`
- **Frontend:** `GET_SENSOR_READINGS` in `airq-fe/src/graphql/SensorReading.ts:29`
- **Used by:** `useRecentSensorReadings` hook and `useCreateSensorReading` (for cache refetch)
- **Issue:** `useRecentSensorReadings` hook is exported from `hooks/index.ts` but **never imported by any component**. It returns all 1000 most recent readings unfiltered. The `useCreateSensorReading` hook references `GET_SENSOR_READINGS` for refetch queries, but this could use `filteredSensorReadings` instead.
- **Action:** Investigate whether `useRecentSensorReadings` is used. If not, remove the hook and potentially the bulk query. Update `useCreateSensorReading` to invalidate relevant cached queries instead.
- **Priority:** Low

### 4.3 `resolve_error_logs` query
- **Backend:** `app/schema.py:3842-3843`
- **Frontend:** `GET_ERROR_LOGS` in `airq-fe/src/graphql/ErrorLog.ts`, `useErrorLogs` hook
- **Issue:** `useErrorLogs` is exported but **never imported by any component**. No UI exists to display error logs.
- **Action:** Remove from frontend. Keep backend query available for debugging/admin use, or remove both.
- **Priority:** Low

### 4.4 `resolve_sensor_locations` query
- **Backend:** `app/schema.py:3815-3819`
- **Frontend:** `GET_SENSOR_LOCATIONS` in `airq-fe/src/graphql/SensorLocation.ts:6`
- **Issue:** The frontend defines this query but needs to be verified if actually consumed by any component. The `GET_CURRENT_ASSIGNMENTS` query on line 16 may be the one actually used.
- **Action:** Verify usage and remove if unused.
- **Priority:** Low

---

## 5. DEAD CODE PATHS

### 5.1 `create_validation_error_response()` - never called in production code
- **File:** `app/validation.py:1226-1249`
- **Issue:** This function creates a standardized error response dictionary, but no resolver in `schema.py` calls it. All resolvers build their own response payloads directly. It is only referenced in `tests/unit/test_validation.py`.
- **Action:** Remove function and its test.
- **Priority:** Low
- **Safe to remove:** Yes.

### 5.2 `log_error()` and `log_performance()` - never called
- **File:** `app/logging_config.py:133-155`
- **Issue:** These helper functions are defined but never imported or called anywhere in the codebase. All logging throughout the app uses `logger.error()` / `logger.info()` directly with `extra={'extra_context': {...}}`.
- **Action:** Remove both functions.
- **Priority:** Low
- **Safe to remove:** Yes.

### 5.3 `clear_cache` import unused in schema.py
- **File:** `app/schema.py:12`
- **Issue:** `clear_cache` is imported from `app.cache` but never called in `schema.py`. No mutation invalidates cache on write.
- **Action:** Either implement cache invalidation in write mutations (e.g., clear cache after `CreateSensorReading`) or remove the unused import.
- **Priority:** Low (removing the import is safe; implementing invalidation would be an improvement)

### 5.4 `cached()` decorator in cache.py - never used
- **File:** `app/cache.py:109-148`
- **Issue:** The `cached()` decorator is defined but never used anywhere. Only `cached_query()` (line 151) is used (by `resolve_filtered_sensor_readings`).
- **Action:** Remove `cached()` decorator if not planned for future use.
- **Priority:** Low
- **Safe to remove:** Yes.

### 5.5 `cache_stats()` and `cleanup_expired()` - never called
- **File:** `app/cache.py:86-106`
- **Issue:** These cache maintenance functions are defined but never called by any code path (no scheduled task, no admin endpoint).
- **Action:** Remove or wire up to an admin/maintenance endpoint.
- **Priority:** Low

### 5.6 `ValidationResult.errors_by_field` property - never used
- **File:** `app/validation.py:35-42`
- **Issue:** This property groups errors by field name but is never called anywhere in the codebase.
- **Action:** Remove.
- **Priority:** Low
- **Safe to remove:** Yes.

---

## 6. REDUNDANT / OVER-ENGINEERED PATTERNS

### 6.1 Validator classes use mutable `self.errors` pattern
- **File:** `app/validation.py` - all validator classes
- **Issue:** Every validator class stores errors in `self.errors`, making them stateful and not thread-safe. The `self.errors = []` reset at the start of each `validate_*` method is easy to forget and could lead to bugs.
- **Action:** Refactor validators to use a local `errors` list within each validation method and return it, rather than storing on `self`. This would make validators stateless and thread-safe.
- **Priority:** Medium

### 6.2 `ResetPassword.mutate` validates password by calling `validate_registration_input` with dummy data
- **File:** `app/schema.py:941-946`
- **Issue:** To validate a new password during reset, the code calls `validate_registration_input(username="dummy", email="dummy@example.com", password=input.new_password)` with fake username and email values. This is a code smell.
- **Action:** Extract a standalone `validate_password()` method in `UserInputValidator` and use it directly.
- **Priority:** Medium

### 6.3 `ChangePassword.mutate` has same dummy validation issue
- **File:** `app/schema.py:1095-1098`
- **Issue:** Same pattern as above - validates password via `validate_registration_input` with full user data just to check password strength.
- **Action:** Same as 6.2 - use a standalone `validate_password()` method.
- **Priority:** Medium

### 6.4 `UpdateProfile.mutate` creates full registration validator just for email check
- **File:** `app/schema.py:1026-1030`
- **Issue:** Creates a `UserInputValidator` and calls `validate_registration_input` with `password="DummyPass1!"` just to check email format. The result is then ignored in favor of manual uniqueness check.
- **Action:** Extract `validate_email()` as a standalone method and use it directly.
- **Priority:** Medium

### 6.5 `GetSensorCalibrationStatus` is a Mutation but should be a Query
- **File:** `app/schema.py:3379-3440`
- **Issue:** This operation only reads data from the sensor (HTTP GET to sensor's `/status` endpoint) and does not modify any state. It should be a Query, not a Mutation. Having it as a mutation requires the frontend to use `useMutation` instead of `useQuery`, losing automatic refetching and caching.
- **Action:** Move to Query class. This would be a breaking change for the frontend.
- **Priority:** Low (works as-is, but semantically incorrect)

### 6.6 `ToggleSensorActive` is redundant with `UpdateSensor`
- **File:** `app/schema.py:2054-2117` (ToggleSensorActive) vs `app/schema.py:1885-1972` (UpdateSensor)
- **Issue:** `ToggleSensorActive` does the same thing as `UpdateSensor` with `is_active` field. It exists as a convenience shortcut, but adds code that must be maintained.
- **Action:** Consider removing and having the frontend use `UpdateSensor` instead. Or keep for API ergonomics.
- **Priority:** Low

---

## 7. ROOT-LEVEL SCRIPTS AUDIT

### 7.1 Migration scripts at project root
- **Files:** `migrate_add_auth_security_fields.py`, `migrate_cameras.py`, `migrate_error_logs.py`, `migrate_ring_devices.py`, `migrate_ring_devices_remove_realtime_fields.py`, `migrate_ring_snapshots.py`, `create_user_table.py`
- **Issue:** These are one-time migration scripts that have already been run. They clutter the project root.
- **Action:** Move to a `migrations/archive/` directory or delete if migration state is tracked elsewhere.
- **Priority:** Low

### 7.2 `simple_test.py` and `test_security.py` at project root
- **Files:** `simple_test.py`, `test_security.py`
- **Issue:** Ad-hoc test files at the project root, separate from the organized `tests/` directory.
- **Action:** Move into `tests/` or delete if superseded by existing test suite.
- **Priority:** Low

### 7.3 `db-dummy-data.py` at project root
- **File:** `db-dummy-data.py`
- **Issue:** Development utility script. Fine to keep but should be in a `scripts/` or `tools/` directory.
- **Action:** Move to `scripts/`.
- **Priority:** Low

---

## 8. ADDITIONAL CLEANUP ITEMS (User-Requested)

### 8.1 Remove Ring Snapshot/Camera Functionality
All Ring integration EXCEPT door sensor functionality should be removed. The `cameras` table is superseded by `ring_devices`.

**Backend removals (airq-api):**
- `Camera` model (models.py:542-561) and `cameras` DB table
- `RingSnapshot` model (models.py:563-580) and `ring_snapshots` DB table
- `idx_ring_snapshots_camera_time` composite index (models.py:709)
- `CameraObject` GraphQL type (schema.py:1174-1183)
- `RingSnapshotObject` GraphQL type (schema.py:1186-1201)
- `CreateRingSnapshotInput` (schema.py:1209-1215)
- `CreateRingSnapshot` mutation (schema.py:1217-1275)
- `CaptureRingSnapshot` mutation (schema.py:1277-1411)
- `resolve_cameras` query (schema.py:3904-3906)
- `resolve_camera` query (schema.py:3908-3919)
- `resolve_ring_snapshots` query (schema.py:3921-3938)
- `resolve_latest_ring_snapshot` query (schema.py:3940-3951)
- `scripts/capture_ring_snapshot.py`
- Migration scripts: `migrate_ring_snapshots.py`, `migrate_cameras.py`

**Frontend removals (airq-fe):**
- `src/graphql/RingSnapshot.ts` (all snapshot/camera queries and mutations)
- `src/hooks/useRingSnapshot.ts`
- `src/components/dashboard/widgets/cards/RingSnapshotCard.tsx`
- `src/components/dashboard/widgets/RingStatusCard.tsx` (combined widget — remove entirely)
- `src/components/dashboard/widgets/cards/RingEventsCard.tsx` (remove or strip camera events)
- `src/pages/api/ring/snapshot.ts`
- `src/pages/api/ring/latest-snapshot.ts`
- `src/pages/api/ring/history.ts` (mixed — remove if primarily camera events)
- `RING_SNAPSHOT` widget definition in `src/config/widgetRegistry.ts`
- `RING_STATUS` widget definition in `src/config/widgetRegistry.ts`
- `RING_EVENTS` widget definition in `src/config/widgetRegistry.ts`
- `RingSnapshotConfig` and `RingEventsConfig` types in `src/types/widgetConfig.ts`
- `ringApiManager.ts` (if only used for snapshot capture — verify door sensors don't need it)

**Door sensor code to KEEP:**
- `RingDevice` model (models.py:582-603)
- `RingDeviceObject`, `RingDeviceInput`, `BatchUpdateRingDevices` (schema.py)
- `resolve_ring_devices`, `resolve_ring_device` queries (schema.py)
- `src/graphql/Ring.ts` (GET_RING_DEVICES, BATCH_UPDATE_RING_DEVICES)
- `src/context/RingContext.tsx`
- `src/services/RingController.ts`
- `src/hooks/useRingDevices.ts`
- `src/components/dashboard/widgets/RingContactSensorCard.tsx`
- `src/pages/api/ring/sync.ts`, `src/pages/api/ring/events.ts`

### 8.2 Rename `sensors.model` to `sensors.hostname`
- Rename column in `sensors` DB table
- Update `Sensor` model field in `models.py`
- Update all references in `schema.py` (GraphQL types, mutations, resolvers)
- Update frontend GraphQL operations, types, and components that reference `model`

---

## 9. IMPLEMENTATION PRIORITY

### Phase 1: Fix Bugs (Immediate)
1. Fix `sensor_reading.timestamp` -> `sensor_reading.reading_time` (schema.py:345)
2. ~~Fix `latest_snapshot.device_id` -> `latest_snapshot.camera_id` (schema.py:1368)~~ — removed with snapshot code
3. ~~Fix `input.device_id` -> `input.camera_id` (schema.py:1264)~~ — removed with snapshot code

### Phase 2: Remove Ring Snapshot/Camera Code (High Priority)
1. Remove backend models, GraphQL types, mutations, and queries for Camera/RingSnapshot
2. Drop `cameras` and `ring_snapshots` tables from DB
3. Remove `scripts/capture_ring_snapshot.py`
4. Remove frontend snapshot components, hooks, API routes, GraphQL operations
5. Remove snapshot widget definitions and types
6. Clean up any imports referencing removed code

### Phase 3: Rename `sensors.model` to `sensors.hostname`
1. Rename DB column
2. Update model, schema, and all backend references
3. Update frontend GraphQL operations, types, and components

### Phase 4: Remove Dead Backend Code (Low Risk)
1. Remove `create_validation_error_response()` from validation.py
2. Remove `log_error()` and `log_performance()` from logging_config.py
3. Remove unused `clear_cache` import from schema.py
4. Remove unused `cached()` decorator from cache.py
5. Remove unused `cache_stats()` and `cleanup_expired()` from cache.py
6. Remove `ValidationResult.errors_by_field` property from validation.py

### Phase 5: Remove Dead GraphQL Endpoints (Coordinate with Frontend)
1. Remove standalone `humidityReadings`, `temperatureReadings`, `co2Readings` queries and their frontend counterparts
2. Remove `useMeasurements.ts`, `useErrorLogs.ts`, `useRecentSensorReadings.ts` hooks (verify no component usage)
3. Remove corresponding `Measurements.ts` and `ErrorLog.ts` GraphQL operation files from frontend
4. Clean up `hooks/index.ts` exports

### Phase 6: Refactor Validators (Medium Effort)
1. Extract standalone `validate_password()` and `validate_email()` methods from `UserInputValidator`
2. Fix password validation in `ResetPassword`, `ChangePassword`, `UpdateProfile` to use extracted methods
3. Consider making validators stateless (local error lists instead of `self.errors`)

### Phase 7: Housekeeping (Low Priority)
1. Archive or delete migration scripts from project root
2. Move ad-hoc test files into `tests/` directory
3. Evaluate `ErrorLog` table utility — implement or remove
4. Evaluate `SensorReading.is_success` column usage
5. Populate or remove `ApplicationErrorLog.user_id` column
