# MongoDB와 Redis 저장 경로 분리 구조

이 프로젝트는 이제 Redis 저장 경로와 MongoDB 저장 경로를 자동으로 묶지 않는다.

## 핵심 의도

- Redis는 메모리 저장소와 TTL, persistence(AOF/RDB)에만 집중한다.
- MongoDB는 별도 저장소/외부 시스템으로 취급한다.
- 따라서 `SET`, `INCR`, `DELETE`, `FLUSHDB` 같은 Redis 명령이 실행되어도 MongoDB에 자동 반영되지 않는다.
- MongoDB 성능과 Redis 메모리 성능을 각각 독립적으로 측정할 수 있다.

## 현재 역할 분리

- `src/mini_redis/engine/redis.py`
  Redis 명령 실행과 메모리 저장소, TTL, persistence를 오케스트레이션한다.
  더 이상 MongoDB write/delete/clear를 직접 호출하지 않는다.

- `src/mini_redis/storage/manager.py`
  Redis용 in-memory hash table 저장소다.
  이 경로가 Redis 자체 저장 성능의 측정 대상이다.

- `src/mini_redis/storage/mongo_adapter.py`
  MongoDB에 실제로 연결해서 `upsert/delete/clear`를 수행하는 가장 바깥 경계다.

- `src/mini_redis/storage/mongo_manager.py`
  Mongo 관련 동작을 감싸는 매니저다.
  Redis 엔진과 별개로 직접 호출하거나 benchmark에서 사용할 수 있다.

- `src/mini_redis/storage/benchmark.py`
  Redis 저장소와 MongoDB 저장소를 각각 따로 벤치마크하기 위한 유틸리티다.

## 벤치마크 방식

### Redis 메모리 저장소 벤치마크

`StorageBenchmarkSuite.benchmark_redis_set(storage, operations)`

- `StorageManager`에 직접 `set()`을 수행한다.
- 네트워크, TCP, RESP, MongoDB를 거치지 않는다.
- 순수 메모리 저장소 성능을 보기 위한 경로다.

### MongoDB 벤치마크

`StorageBenchmarkSuite.benchmark_mongo_write(mongo, operations)`

- `MongoManager.write_value()`를 직접 호출한다.
- Redis 엔진을 거치지 않는다.
- 외부 MongoDB 연결 및 write 성능을 보기 위한 경로다.

`StorageBenchmarkSuite.benchmark_mongo_delete(mongo, operations)`

- `MongoManager.delete_key()`를 직접 호출한다.
- 삭제 성능 측정용 경로다.

## 왜 이렇게 분리했는가

이전 구조에서는 Redis 명령이 실행되면 MongoDB까지 같이 쓰였기 때문에:

- Redis 자체 성능인지
- MongoDB 네트워크/디스크 비용 때문인지

구분하기 어려웠다.

지금 구조에서는 두 저장 경로를 독립적으로 측정할 수 있어서:

- Redis 메모리 성능
- MongoDB 외부 저장 성능

을 따로 분석할 수 있다.
