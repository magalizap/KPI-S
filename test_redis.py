#!/usr/bin/env python
"""
Script de prueba para validar conexión a Redis y estado del caché.
Uso: python test_redis.py
"""

import sys
import redis
from datetime import datetime, timedelta

# Cargar secrets
try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib

try:
    with open(".streamlit/secrets.toml", "rb") as f:
        secrets = tomllib.load(f)
except FileNotFoundError:
    print("❌ No se encontró .streamlit/secrets.toml")
    sys.exit(1)

redis_url = secrets.get("redis_url")
if not redis_url:
    print("[ERROR] 'redis_url' no está en secrets.toml")
    sys.exit(1)

print(f"[INFO] Redis URL: {redis_url}")
print("-" * 60)

try:
    r = redis.from_url(redis_url, decode_responses=False)
    r.ping()
    print("[OK] Conexión a Redis: OK\n")
    
    # Info del servidor
    info = r.info()
    print(f"[INFO] Redis Server Info:")
    print(f"   Versión: {info.get('redis_version', 'N/A')}")
    print(f"   Modo: {'cluster' if info.get('cluster_enabled') else 'standalone'}")
    print(f"   Memoria usada: {info.get('used_memory_human', 'N/A')}")
    print()
    
    # Contar keys por tipo
    db_info = info.get('keyspace', {})
    total_keys = sum(int(v.split(',')[0].split('=')[1]) for v in db_info.values() if 'keys=' in v)
    print(f"[INFO] Total de keys en Redis: {total_keys}\n")
    
    # Listar keys del caché
    keys = list(r.scan_iter("*", count=100))
    if keys:
        print(f"[INFO] Keys en caché ({len(keys)}):")
        for key in sorted(keys)[:20]:  # Primeras 20
            key_decoded = key.decode('utf-8') if isinstance(key, bytes) else key
            ttl = r.ttl(key)
            ttl_str = f"{ttl}s" if ttl > 0 else "sin expiración" if ttl == -1 else "expirado"
            print(f"   • {key_decoded:<50} TTL: {ttl_str}")
        if len(keys) > 20:
            print(f"   ... y {len(keys) - 20} más")
    else:
        print("   (Sin datos en caché)")
    
    print("\n" + "=" * 60)
    print("[OK] Redis está operacional y listo para usar")
    
except redis.ConnectionError as e:
    print(f"[ERROR] No se puede conectar a Redis:")
    print(f"   {e}")
    print("\n[INFO] Asegúrate de que Redis esté corriendo:")
    print("   - En Windows: redis-server o Docker")
    print("   - Verifica redis_url en .streamlit/secrets.toml")
    sys.exit(1)
    
except Exception as e:
    print(f"[ERROR] Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
