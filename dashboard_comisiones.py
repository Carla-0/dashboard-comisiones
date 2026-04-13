#!/usr/bin/env python3
"""
Dashboard de Comisiones - Zyra Brokers
Servidor web con dashboard interactivo para visualización de comisiones.

Uso:
    pip install pymysql
    python dashboard_comisiones.py

Luego abre http://localhost:8080 en tu navegador.
"""

import json
import http.server
import socketserver
import urllib.parse
from datetime import date, datetime
import os
import sys

try:
    import pymysql
except ImportError:
    print("=" * 60)
    print("  PyMySQL no está instalado.")
    print("  Ejecuta: pip install pymysql")
    print("=" * 60)
    sys.exit(1)

# ─── Configuración de Base de Datos ───
# Usa variables de entorno para seguridad
# Para uso local, crea un archivo .env o configura las variables antes de ejecutar
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", ""),
    "database": os.environ.get("DB_NAME", ""),
    "user": os.environ.get("DB_USER", ""),
    "password": os.environ.get("DB_PASSWORD", ""),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}

TABLE = "DashbordLk"

COLUMN_MAP = {
    "aseguradora": "DashbordLkAseguradora",
    "ejecutivo": "DashbordLkEjecutivo",
    "estado": "DashbordLkEstado",
    "estado_pago": "DashbordLkEstadoPago",
    "fecha_emision": "DashbordLkFechaEmision",
    "fee_neto_usd": "DashbordLkFeeNetoUSD",
    "fin_vigencia": "DashbordLkFinVigencia",
    "inicio_vigencia": "DashbordLkInicioVigencia",
    "mc_producer_usd": "DashbordLkMCProducerUSD",
    "mc_zyra_usd": "DashbordLkMCZyraUSD",
    "moneda": "DashbordLkMoneda",
    "prima_neta_usd": "DashbordLkPrimaNetaUSD",
    "producer": "DashbordLkProducer",
    "ramo": "DashbordLkRamo",
    "razon_social": "DashbordLkRazonSocial",
    "tipo_venta": "DashbordLkTipoVenta",
}

PORT = int(os.environ.get("PORT", 8080))


def get_connection():
    return pymysql.connect(**DB_CONFIG)


def json_serial(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def fetch_all_data(filters=None):
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            query = f"SELECT * FROM {TABLE} WHERE 1=1"
            params = []

            if filters:
                if filters.get("inicio_desde"):
                    query += f" AND {COLUMN_MAP['inicio_vigencia']} >= %s"
                    params.append(filters["inicio_desde"])
                if filters.get("inicio_hasta"):
                    query += f" AND {COLUMN_MAP['inicio_vigencia']} <= %s"
                    params.append(filters["inicio_hasta"])
                for fkey in ["producer", "razon_social", "aseguradora", "ejecutivo", "estado_pago"]:
                    if filters.get(fkey):
                        values = [v.strip() for v in filters[fkey].split("||") if v.strip()]
                        if values:
                            placeholders = ",".join(["%s"] * len(values))
                            query += f" AND {COLUMN_MAP[fkey]} IN ({placeholders})"
                            params.extend(values)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return rows
    finally:
        conn.close()


def fetch_filter_options():
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            options = {}
            for key in ["producer", "razon_social", "aseguradora", "ejecutivo", "estado_pago"]:
                col = COLUMN_MAP[key]
                cursor.execute(f"SELECT DISTINCT {col} FROM {TABLE} WHERE {col} IS NOT NULL AND {col} != '' ORDER BY {col}")
                options[key] = [row[col] for row in cursor.fetchall()]
            return options
    finally:
        conn.close()


def compute_dashboard(data):
    """Compute all dashboard metrics from raw data."""
    if not data:
        return {
            "kpis": {},
            "top_contratantes_fee": [],
            "top_contratantes_mc_producer": [],
            "top_ramos_prima": [],
            "top_ramos_mc_zyra": [],
            "estado_pago": [],
            "timeline": [],
            "total_records": 0,
        }

    # Helper to safely convert to float
    def safe_float(val):
        try:
            return float(val) if val is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    total_fee = sum(safe_float(r.get(COLUMN_MAP["fee_neto_usd"])) for r in data)
    total_mc_producer = sum(safe_float(r.get(COLUMN_MAP["mc_producer_usd"])) for r in data)
    total_mc_zyra = sum(safe_float(r.get(COLUMN_MAP["mc_zyra_usd"])) for r in data)
    total_prima = sum(safe_float(r.get(COLUMN_MAP["prima_neta_usd"])) for r in data)

    # KPIs
    kpis = {
        "total_fee_neto": round(total_fee, 2),
        "total_mc_producer": round(total_mc_producer, 2),
        "total_mc_zyra": round(total_mc_zyra, 2),
        "total_prima_neta": round(total_prima, 2),
        "total_polizas": len(data),
    }

    # Top Contratantes by Fee Neto
    contratante_fee = {}
    contratante_mc_producer = {}
    for r in data:
        rs = r.get(COLUMN_MAP["razon_social"], "N/A") or "N/A"
        contratante_fee[rs] = contratante_fee.get(rs, 0) + safe_float(r.get(COLUMN_MAP["fee_neto_usd"]))
        contratante_mc_producer[rs] = contratante_mc_producer.get(rs, 0) + safe_float(r.get(COLUMN_MAP["mc_producer_usd"]))

    top_contratantes_fee = sorted(contratante_fee.items(), key=lambda x: x[1], reverse=True)[:10]
    top_contratantes_mc_producer = sorted(contratante_mc_producer.items(), key=lambda x: x[1], reverse=True)[:10]

    # Top Ramos by Prima Neta
    ramo_prima = {}
    ramo_mc_zyra = {}
    for r in data:
        ramo = r.get(COLUMN_MAP["ramo"], "N/A") or "N/A"
        ramo_prima[ramo] = ramo_prima.get(ramo, 0) + safe_float(r.get(COLUMN_MAP["prima_neta_usd"]))
        ramo_mc_zyra[ramo] = ramo_mc_zyra.get(ramo, 0) + safe_float(r.get(COLUMN_MAP["mc_zyra_usd"]))

    top_ramos_prima = sorted(ramo_prima.items(), key=lambda x: x[1], reverse=True)[:10]
    top_ramos_mc_zyra = sorted(ramo_mc_zyra.items(), key=lambda x: x[1], reverse=True)[:10]

    # Estado de Pago
    estado_pago_map = {}
    for r in data:
        ep = r.get(COLUMN_MAP["estado_pago"], "Sin estado") or "Sin estado"
        if ep not in estado_pago_map:
            estado_pago_map[ep] = {"count": 0, "prima_neta": 0, "fee_neto": 0}
        estado_pago_map[ep]["count"] += 1
        estado_pago_map[ep]["prima_neta"] += safe_float(r.get(COLUMN_MAP["prima_neta_usd"]))
        estado_pago_map[ep]["fee_neto"] += safe_float(r.get(COLUMN_MAP["fee_neto_usd"]))

    estado_pago_list = [
        {"estado": k, "count": v["count"], "prima_neta": round(v["prima_neta"], 2), "fee_neto": round(v["fee_neto"], 2)}
        for k, v in estado_pago_map.items()
    ]

    # Timeline by month (inicio_vigencia)
    timeline_map = {}
    for r in data:
        iv = r.get(COLUMN_MAP["inicio_vigencia"])
        if iv:
            if isinstance(iv, str):
                try:
                    iv = datetime.strptime(iv[:10], "%Y-%m-%d")
                except:
                    continue
            month_key = iv.strftime("%Y-%m")
            if month_key not in timeline_map:
                timeline_map[month_key] = {"prima_neta": 0, "fee_neto": 0, "mc_zyra": 0, "count": 0}
            timeline_map[month_key]["prima_neta"] += safe_float(r.get(COLUMN_MAP["prima_neta_usd"]))
            timeline_map[month_key]["fee_neto"] += safe_float(r.get(COLUMN_MAP["fee_neto_usd"]))
            timeline_map[month_key]["mc_zyra"] += safe_float(r.get(COLUMN_MAP["mc_zyra_usd"]))
            timeline_map[month_key]["count"] += 1

    timeline = sorted(
        [{"month": k, "prima_neta": round(v["prima_neta"], 2), "fee_neto": round(v["fee_neto"], 2), "mc_zyra": round(v["mc_zyra"], 2), "count": v["count"]} for k, v in timeline_map.items()],
        key=lambda x: x["month"],
    )

    # Top Producers
    producer_map = {}
    for r in data:
        p = r.get(COLUMN_MAP["producer"], "N/A") or "N/A"
        if p not in producer_map:
            producer_map[p] = {"fee_neto": 0, "mc_producer": 0, "prima_neta": 0, "count": 0}
        producer_map[p]["fee_neto"] += safe_float(r.get(COLUMN_MAP["fee_neto_usd"]))
        producer_map[p]["mc_producer"] += safe_float(r.get(COLUMN_MAP["mc_producer_usd"]))
        producer_map[p]["prima_neta"] += safe_float(r.get(COLUMN_MAP["prima_neta_usd"]))
        producer_map[p]["count"] += 1

    top_producers = sorted(
        [{"producer": k, "fee_neto": round(v["fee_neto"], 2), "mc_producer": round(v["mc_producer"], 2), "prima_neta": round(v["prima_neta"], 2), "count": v["count"]} for k, v in producer_map.items()],
        key=lambda x: x["fee_neto"],
        reverse=True,
    )[:10]

    return {
        "kpis": kpis,
        "top_contratantes_fee": [{"name": n, "value": round(v, 2)} for n, v in top_contratantes_fee],
        "top_contratantes_mc_producer": [{"name": n, "value": round(v, 2)} for n, v in top_contratantes_mc_producer],
        "top_ramos_prima": [{"name": n, "value": round(v, 2)} for n, v in top_ramos_prima],
        "top_ramos_mc_zyra": [{"name": n, "value": round(v, 2)} for n, v in top_ramos_mc_zyra],
        "estado_pago": estado_pago_list,
        "timeline": timeline,
        "top_producers": top_producers,
        "total_records": len(data),
    }


# ─── Embedded SVG Logo ───
LOGO_SVG = '''<?xml version="1.0" encoding="UTF-8"?>
<svg id="Capa_1" data-name="Capa 1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 689.39 253.23">
  <defs>
    <style>
      .cls-1 { fill: url(#Degradado_sin_nombre_6); }
      .cls-2 { fill: url(#Degradado_sin_nombre_2105); }
      .cls-3 { fill: #042644; }
      .cls-4 { fill: url(#Degradado_sin_nombre_1825); }
    </style>
    <linearGradient id="Degradado_sin_nombre_6" data-name="Degradado sin nombre 6" x1="113.9" y1="227.8" x2="113.9" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#3642b5"/>
      <stop offset="1" stop-color="#eaecfe"/>
    </linearGradient>
    <linearGradient id="Degradado_sin_nombre_1825" data-name="Degradado sin nombre 1825" x1="113.9" y1="227.8" x2="113.9" y2="60.8" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#92b2f5"/>
      <stop offset="1" stop-color="#ebebeb"/>
    </linearGradient>
    <linearGradient id="Degradado_sin_nombre_2105" data-name="Degradado sin nombre 2105" x1="113.9" y1="174.69" x2="113.9" y2="60.8" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#fff" stop-opacity=".4"/>
      <stop offset=".15" stop-color="#f7f7fd" stop-opacity=".43"/>
      <stop offset=".35" stop-color="#e2e2f8" stop-opacity=".52"/>
      <stop offset=".59" stop-color="#bfc0f1" stop-opacity=".67"/>
      <stop offset=".85" stop-color="#8f91e6" stop-opacity=".87"/>
      <stop offset="1" stop-color="#7072e0"/>
    </linearGradient>
  </defs>
  <g>
    <circle class="cls-1" cx="113.9" cy="113.9" r="113.9"/>
    <circle class="cls-4" cx="113.9" cy="144.3" r="83.5"/>
    <circle class="cls-2" cx="113.9" cy="117.74" r="56.95"/>
  </g>
  <g>
    <g>
      <path class="cls-3" d="M367.03,60.02v26.74l-86.62,70.05h86.62v15.03h-92.59v-26.74l86.62-70.05h-86.62v-15.03h92.59Z"/>
      <path class="cls-3" d="M473.54,60.02h17.01l-57.89,156h-17.01l16.57-44.19h-13.04l-41.76-111.81h18.12l38.45,106.95,39.55-106.95Z"/>
      <path class="cls-3" d="M522.15,90.08c8.18-26.96,25.85-34.91,45.52-31.38v16.13c-24.97-5.52-45.52,9.5-45.52,33.15v63.86h-16.57V60.02h16.57v30.05Z"/>
      <path class="cls-3" d="M671.53,60.02h16.57v111.81h-16.57v-32.48c-7.51,20.77-25.19,34.69-47.51,34.69-30.27,0-53.03-24.97-53.03-58.11s22.76-58.12,53.03-58.12c22.32,0,40,13.92,47.51,34.69v-32.48ZM671.53,115.93c0-24.31-17.9-42.65-42.87-42.65-22.54,0-40.66,18.34-40.66,42.65s18.12,42.65,40.66,42.65c24.97,0,42.87-18.34,42.87-42.65Z"/>
    </g>
    <g>
      <g>
        <path class="cls-3" d="M506.29,190.81h8.85c4.46,0,7.51,3.05,7.51,7.01s-3.05,6.97-7.51,6.97h-6.24v9.49h-2.61v-23.46ZM515.14,202.41c2.85,0,4.83-2.01,4.83-4.63s-1.98-4.59-4.83-4.59h-6.24v9.22h6.24Z"/>
        <path class="cls-3" d="M532.24,196.98c5.06,0,8.92,3.82,8.92,8.82s-3.85,8.82-8.92,8.82-8.92-3.79-8.92-8.82,3.86-8.82,8.92-8.82ZM532.24,212.26c3.62,0,6.33-2.78,6.33-6.47s-2.71-6.47-6.33-6.47-6.34,2.78-6.34,6.47,2.75,6.47,6.34,6.47Z"/>
        <path class="cls-3" d="M541.96,197.31h2.51l4.76,16.22,4.19-16.22h4.53l4.19,16.29,4.76-16.29h2.45l-5.16,16.96h-4.16l-4.36-16.22-4.39,16.22h-4.16l-5.16-16.96Z"/>
        <path class="cls-3" d="M579.24,196.98c5.2,0,9.08,4.16,8.68,9.59h-14.92c.37,3.35,2.98,5.8,6.44,5.8,2.65,0,4.79-1.41,5.87-3.62l2.15.91c-1.37,2.92-4.29,4.96-8.04,4.96-5.06,0-8.92-3.79-8.92-8.82s3.79-8.82,8.75-8.82ZM585.37,204.49c-.5-2.98-2.92-5.26-6.13-5.26s-5.6,2.21-6.17,5.26h12.3Z"/>
        <path class="cls-3" d="M591.61,197.31h2.51v4.56c1.24-4.09,3.92-5.3,6.91-4.76v2.45c-3.79-.84-6.91,1.44-6.91,5.03v9.69h-2.51v-16.96Z"/>
        <path class="cls-3" d="M610.28,196.98c5.2,0,9.08,4.16,8.68,9.59h-14.92c.37,3.35,2.98,5.8,6.44,5.8,2.65,0,4.79-1.41,5.87-3.62l2.15.91c-1.37,2.92-4.29,4.96-8.04,4.96-5.06,0-8.92-3.79-8.92-8.82s3.79-8.82,8.75-8.82ZM616.41,204.49c-.5-2.98-2.92-5.26-6.13-5.26s-5.6,2.21-6.17,5.26h12.3Z"/>
        <path class="cls-3" d="M629.79,196.98c3.39,0,6.07,2.11,7.21,5.26v-12.77h2.51v24.81h-2.51v-4.93c-1.14,3.15-3.82,5.26-7.21,5.26-4.59,0-8.05-3.79-8.05-8.82s3.45-8.82,8.05-8.82ZM630.49,212.26c3.79,0,6.5-2.78,6.5-6.47s-2.71-6.47-6.5-6.47c-3.42,0-6.17,2.78-6.17,6.47s2.75,6.47,6.17,6.47Z"/>
        <path class="cls-3" d="M653.86,189.47h2.51v12.87c1.11-3.22,3.79-5.36,7.21-5.36,4.59,0,8.04,3.82,8.04,8.82s-3.45,8.82-8.04,8.82c-3.42,0-6.1-2.15-7.21-5.33v4.99h-2.51v-24.81ZM662.87,212.26c3.45,0,6.17-2.78,6.17-6.47s-2.72-6.47-6.17-6.47c-3.75,0-6.5,2.78-6.5,6.47s2.75,6.47,6.5,6.47Z"/>
        <path class="cls-3" d="M680.54,214.27h-1.98l-6.34-16.96h2.75l5.83,16.22,6-16.22h2.58l-8.78,23.67h-2.58l2.51-6.7Z"/>
      </g>
      <g>
        <path class="cls-3" d="M617.85,229.58c-.57-.54-.85-1.23-.85-2.08s.28-1.52.85-2.06c.57-.54,1.25-.81,2.05-.81,1.53-.03,2.91,1.2,2.88,2.86,0,.85-.28,1.54-.85,2.08-.56.54-1.24.81-2.03.81s-1.48-.27-2.05-.8ZM621.76,225.59c-.51-.5-1.13-.74-1.87-.74s-1.36.25-1.88.75c-.52.5-.78,1.13-.78,1.91s.26,1.42.77,1.92c.52.5,1.15.75,1.88.75s1.36-.25,1.87-.75c.51-.5.77-1.14.77-1.93s-.26-1.41-.77-1.9ZM618.81,228.63c-.29-.29-.44-.66-.44-1.12s.15-.83.44-1.12c.29-.29.67-.43,1.13-.43.4,0,.73.11,1.01.34.28.22.43.51.47.87h-.56c-.06-.43-.43-.72-.92-.72-.62,0-.99.43-.99,1.07s.38,1.07.99,1.07c.5,0,.87-.29.93-.71h.56c-.04.34-.2.63-.48.86-.27.22-.61.34-1.01.34-.45,0-.83-.15-1.12-.43Z"/>
        <g>
          <path class="cls-3" d="M511.67,248.43l13.25-14.62v-4.71h-18.62v3.98h13.33l-13.24,14.62v4.72h19.14v-3.98h-13.86Z"/>
          <path class="cls-3" d="M550.21,239.86c0-1.5-.26-2.95-.77-4.34-.52-1.39-1.28-2.62-2.3-3.69-1.02-1.07-2.29-1.93-3.82-2.58-1.53-.65-3.32-.98-5.35-.98s-3.93.35-5.49,1.04c-1.56.69-2.87,1.6-3.92,2.73-1.05,1.13-1.83,2.41-2.34,3.85-.52,1.45-.77,2.92-.77,4.42v.82c0,1.47.25,2.93.75,4.38.5,1.44,1.28,2.74,2.34,3.88,1.06,1.14,2.39,2.07,3.99,2.77,1.59.71,3.5,1.06,5.72,1.06,3.03,0,5.57-.7,7.62-2.1,2.05-1.4,3.34-3.32,3.87-5.77h-5.11c-.25.98-.93,1.82-2.04,2.51-1.11.69-2.56,1.04-4.34,1.04-1.22,0-2.28-.17-3.19-.52-.91-.35-1.67-.83-2.3-1.45-.63-.62-1.1-1.35-1.43-2.2-.33-.85-.54-1.8-.63-2.83h19.51v-2.04ZM530.83,238.48c.34-1.83,1.1-3.27,2.27-4.33,1.17-1.06,2.79-1.59,4.86-1.59s3.67.53,4.81,1.59c1.14,1.06,1.84,2.51,2.09,4.33h-14.02Z"/>
          <path class="cls-3" d="M606.57,239.05l9.01-9.95h-5.82l-10.23,11.46v-11.46h-5.49v23.31h5.49v-10.86h3.05l9.01,10.86h6.29l-11.31-13.36Z"/>
          <path class="cls-3" d="M586.15,229.1v13.9c0,1.74-.54,3.11-1.62,4.1-1.08,1-2.46,1.5-4.15,1.5s-2.97-.46-3.94-1.39c-.97-.93-1.45-2.22-1.45-3.87v-14.25h-5.49v13.54c0,3.5.79,6.14,2.37,7.92,1.58,1.78,3.87,2.67,6.87,2.67h.23c4.38,0,7.15-2.05,8.3-6.14v5.32h4.36v-23.31h-5.49Z"/>
          <path class="cls-3" d="M566.23,228.84c-5.44,0-8.54,2.45-9.29,7.35v-7.09h-4.36v23.31h5.49v-12.37c0-2.16.63-3.83,1.9-5,1.27-1.17,3.09-1.75,5.46-1.75h1.69v-4.45h-.89Z"/>
        </g>
      </g>
    </g>
  </g>
</svg>'''


# ─── HTML Dashboard ───
DASHBOARD_HTML = r'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard de Comisiones - Zyra</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root {
    --primary: #3642b5;
    --primary-light: #4a55c9;
    --primary-dark: #042644;
    --accent: #92b2f5;
    --accent2: #7072e0;
    --bg: #f0f2f8;
    --card: #ffffff;
    --text: #1a1a2e;
    --text-muted: #6b7280;
    --border: #e2e5f1;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --gradient-1: linear-gradient(135deg, #3642b5 0%, #7072e0 100%);
    --gradient-2: linear-gradient(135deg, #042644 0%, #3642b5 100%);
    --gradient-3: linear-gradient(135deg, #92b2f5 0%, #eaecfe 100%);
    --shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
    --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -2px rgba(0,0,0,0.04);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
}

/* ─── Header ─── */
.header {
    background: var(--gradient-2);
    padding: 16px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 4px 12px rgba(4, 38, 68, 0.3);
    position: sticky;
    top: 0;
    z-index: 100;
}
.header-left { display: flex; align-items: center; gap: 16px; }
.header-left svg { height: 48px; width: auto; }
.header-title { color: white; }
.header-title h1 { font-size: 20px; font-weight: 600; letter-spacing: 0.5px; }
.header-title p { font-size: 12px; opacity: 0.7; margin-top: 2px; }
.header-right { display: flex; align-items: center; gap: 12px; }
.refresh-btn {
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.25);
    color: white;
    padding: 8px 16px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.2s;
}
.refresh-btn:hover { background: rgba(255,255,255,0.25); }
.refresh-btn.loading { opacity: 0.6; pointer-events: none; }
.record-count {
    background: rgba(255,255,255,0.1);
    padding: 6px 14px;
    border-radius: 20px;
    color: rgba(255,255,255,0.9);
    font-size: 13px;
}

/* ─── Filters ─── */
.filters-bar {
    background: white;
    padding: 16px 32px;
    border-bottom: 1px solid var(--border);
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    align-items: flex-end;
}
.filter-group { display: flex; flex-direction: column; gap: 4px; }
.filter-group label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.filter-group input[type="date"] {
    padding: 7px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 13px;
    color: var(--text);
    background: white;
    min-width: 140px;
    outline: none;
    transition: border-color 0.2s;
}
.filter-group input[type="date"]:focus {
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(54, 66, 181, 0.1);
}
.filter-actions { display: flex; gap: 8px; align-items: flex-end; }
.btn-filter {
    padding: 7px 20px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    transition: all 0.2s;
}
.btn-clear { background: var(--bg); color: var(--text-muted); border: 1px solid var(--border); }
.btn-clear:hover { background: #e5e7eb; }

/* ─── Multi-Select Dropdown ─── */
.ms-wrapper { position: relative; min-width: 180px; }
.ms-trigger {
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 13px;
    color: var(--text);
    background: white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
    min-height: 34px;
    transition: border-color 0.2s;
}
.ms-trigger:hover { border-color: #b0b8d1; }
.ms-trigger.active { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(54,66,181,0.1); }
.ms-trigger .ms-text { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ms-trigger .ms-arrow { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }
.ms-badge {
    background: var(--primary);
    color: white;
    font-size: 11px;
    padding: 1px 6px;
    border-radius: 10px;
    flex-shrink: 0;
}
.ms-dropdown {
    display: none;
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    width: 280px;
    max-height: 320px;
    background: white;
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.12);
    z-index: 200;
    flex-direction: column;
}
.ms-dropdown.open { display: flex; }
.ms-search {
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
    outline: none;
    border-radius: 8px 8px 0 0;
}
.ms-options {
    overflow-y: auto;
    flex: 1;
    max-height: 240px;
}
.ms-option {
    padding: 6px 10px;
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 13px;
    transition: background 0.1s;
}
.ms-option:hover { background: #f0f2ff; }
.ms-option input[type="checkbox"] {
    accent-color: var(--primary);
    width: 15px;
    height: 15px;
    cursor: pointer;
    flex-shrink: 0;
}
.ms-option span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ms-footer {
    padding: 6px 10px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.ms-footer button {
    background: none;
    border: none;
    font-size: 12px;
    cursor: pointer;
    padding: 3px 8px;
    border-radius: 4px;
}
.ms-footer .ms-select-all { color: var(--primary); }
.ms-footer .ms-select-all:hover { background: #eef2ff; }
.ms-footer .ms-clear-btn { color: var(--danger); }
.ms-footer .ms-clear-btn:hover { background: #fef2f2; }
.ms-count { font-size: 11px; color: var(--text-muted); }

/* ─── Main Content ─── */
.main { padding: 24px 32px; max-width: 1600px; margin: 0 auto; }

/* ─── KPI Cards ─── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}
.kpi-card {
    background: white;
    border-radius: 12px;
    padding: 20px;
    box-shadow: var(--shadow);
    border-left: 4px solid var(--primary);
    transition: transform 0.2s, box-shadow 0.2s;
}
.kpi-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-lg); }
.kpi-card:nth-child(1) { border-left-color: var(--primary); }
.kpi-card:nth-child(2) { border-left-color: var(--accent2); }
.kpi-card:nth-child(3) { border-left-color: var(--accent); }
.kpi-card:nth-child(4) { border-left-color: var(--success); }
.kpi-card:nth-child(5) { border-left-color: var(--warning); }
.kpi-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
}
.kpi-value {
    font-size: 24px;
    font-weight: 700;
    color: var(--primary-dark);
}

/* ─── Chart Grid ─── */
.chart-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 24px;
}
.chart-card {
    background: white;
    border-radius: 12px;
    padding: 20px;
    box-shadow: var(--shadow);
}
.chart-card.full-width { grid-column: 1 / -1; }
.chart-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--primary-dark);
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.chart-title .icon {
    width: 28px;
    height: 28px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
}
.chart-container { position: relative; height: 300px; }
.chart-container.tall { height: 350px; }

/* ─── Estado Pago Table ─── */
.estado-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 13px;
}
.estado-table th {
    background: var(--bg);
    padding: 10px 14px;
    text-align: left;
    font-weight: 600;
    color: var(--text-muted);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    border-bottom: 2px solid var(--border);
}
.estado-table td {
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
}
.estado-table tr:last-child td { border-bottom: none; }
.estado-table tr:hover td { background: #f8f9ff; }
.estado-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
}
.badge-pagado { background: #d1fae5; color: #065f46; }
.badge-pendiente { background: #fef3c7; color: #92400e; }
.badge-default { background: #e5e7eb; color: #374151; }

/* ─── Loading ─── */
.loading-overlay {
    position: fixed;
    inset: 0;
    background: rgba(255,255,255,0.9);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 999;
    backdrop-filter: blur(6px);
}
.loading-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 20px;
}
.loading-logo {
    animation: logoSpin 1.8s ease-in-out infinite;
}
.loading-logo svg {
    height: 80px;
    width: auto;
    filter: drop-shadow(0 4px 12px rgba(54, 66, 181, 0.3));
}
@keyframes logoSpin {
    0% { transform: rotateY(0deg) scale(1); }
    50% { transform: rotateY(180deg) scale(1.05); }
    100% { transform: rotateY(360deg) scale(1); }
}
.loading-text {
    font-size: 15px;
    font-weight: 500;
    color: var(--primary);
    letter-spacing: 0.5px;
}
.loading-dots::after {
    content: '';
    animation: dots 1.5s steps(4, end) infinite;
}
@keyframes dots {
    0% { content: ''; }
    25% { content: '.'; }
    50% { content: '..'; }
    75% { content: '...'; }
}
.hidden { display: none !important; }

/* ─── Responsive ─── */
@media (max-width: 1200px) {
    .kpi-grid { grid-template-columns: repeat(3, 1fr); }
    .chart-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
    .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    .header { padding: 12px 16px; }
    .main { padding: 16px; }
    .filters-bar { padding: 12px 16px; }
}
</style>
</head>
<body>

<div class="loading-overlay" id="loadingOverlay">
    <div class="loading-content">
        <div class="loading-logo" id="loadingLogoSvg"></div>
        <div class="loading-text">Cargando datos<span class="loading-dots"></span></div>
    </div>
</div>

<!-- Header -->
<div class="header">
    <div class="header-left">
        <div id="logoContainer"></div>
        <div class="header-title">
            <h1>Dashboard de Comisiones</h1>
            <p>Panel de control y análisis financiero</p>
        </div>
    </div>
    <div class="header-right">
        <span class="record-count" id="lastUpdate" style="background:rgba(16,185,129,0.2);color:#d1fae5;">Actualizando...</span>
        <span class="record-count" id="recordCount">0 registros</span>
        <button class="refresh-btn" onclick="loadData()">
            <span>&#x21bb;</span> Actualizar
        </button>
    </div>
</div>

<!-- Filters -->
<div class="filters-bar">
    <div class="filter-group">
        <label>Inicio Vigencia Desde</label>
        <input type="date" id="filterDesde">
    </div>
    <div class="filter-group">
        <label>Inicio Vigencia Hasta</label>
        <input type="date" id="filterHasta">
    </div>
    <div class="filter-group">
        <label>Producer</label>
        <div class="ms-wrapper" id="msProducer" data-key="producer"></div>
    </div>
    <div class="filter-group">
        <label>Razón Social</label>
        <div class="ms-wrapper" id="msRazonSocial" data-key="razon_social"></div>
    </div>
    <div class="filter-group">
        <label>Aseguradora</label>
        <div class="ms-wrapper" id="msAseguradora" data-key="aseguradora"></div>
    </div>
    <div class="filter-group">
        <label>Ejecutivo</label>
        <div class="ms-wrapper" id="msEjecutivo" data-key="ejecutivo"></div>
    </div>
    <div class="filter-group">
        <label>Estado de Pago</label>
        <div class="ms-wrapper" id="msEstadoPago" data-key="estado_pago"></div>
    </div>
    <div class="filter-actions">
        <button class="btn-filter btn-clear" onclick="clearFilters()">Limpiar filtros</button>
    </div>
</div>

<!-- Main Content -->
<div class="main">
    <!-- KPIs -->
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Fee Neto USD Total</div>
            <div class="kpi-value" id="kpiFeeNeto">$0.00</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Comisión Producer USD</div>
            <div class="kpi-value" id="kpiMcProducer">$0.00</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Comisión Zyra USD</div>
            <div class="kpi-value" id="kpiMcZyra">$0.00</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Prima Neta USD Total</div>
            <div class="kpi-value" id="kpiPrimaNeta">$0.00</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Total Pólizas</div>
            <div class="kpi-value" id="kpiPolizas">0</div>
        </div>
    </div>

    <!-- Charts Row 1 -->
    <div class="chart-grid">
        <div class="chart-card">
            <div class="chart-title">
                <div class="icon" style="background:#eef2ff;color:var(--primary);">&#x1f4b0;</div>
                Top Contratantes por Fee Neto USD
            </div>
            <div class="chart-container"><canvas id="chartContratantesFee"></canvas></div>
        </div>
        <div class="chart-card">
            <div class="chart-title">
                <div class="icon" style="background:#f0fdf4;color:var(--success);">&#x1f4c8;</div>
                Top Contratantes por Comisión Producer USD
            </div>
            <div class="chart-container"><canvas id="chartContratantesMcProducer"></canvas></div>
        </div>
    </div>

    <!-- Charts Row 2 -->
    <div class="chart-grid">
        <div class="chart-card">
            <div class="chart-title">
                <div class="icon" style="background:#fef3c7;color:var(--warning);">&#x1f4ca;</div>
                Top Ramos por Prima Neta USD
            </div>
            <div class="chart-container"><canvas id="chartRamosPrima"></canvas></div>
        </div>
        <div class="chart-card">
            <div class="chart-title">
                <div class="icon" style="background:#ede9fe;color:#7c3aed;">&#x1f4c9;</div>
                Top Ramos por Comisión Zyra USD
            </div>
            <div class="chart-container"><canvas id="chartRamosMcZyra"></canvas></div>
        </div>
    </div>

    <!-- Estado de Pago + Timeline -->
    <div class="chart-grid">
        <div class="chart-card">
            <div class="chart-title">
                <div class="icon" style="background:#fce7f3;color:#db2777;">&#x2705;</div>
                Estado de Pago
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
                <div class="chart-container" style="height:250px;"><canvas id="chartEstadoPago"></canvas></div>
                <div>
                    <table class="estado-table" id="estadoPagoTable">
                        <thead>
                            <tr>
                                <th>Estado</th>
                                <th style="text-align:right;">Pólizas</th>
                                <th style="text-align:right;">Prima Neta USD</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </div>
        <div class="chart-card">
            <div class="chart-title">
                <div class="icon" style="background:#dbeafe;color:#2563eb;">&#x1f4c5;</div>
                Top Producers por Fee Neto USD
            </div>
            <div class="chart-container"><canvas id="chartProducers"></canvas></div>
        </div>
    </div>

    <!-- Timeline Full Width -->
    <div class="chart-grid">
        <div class="chart-card full-width">
            <div class="chart-title">
                <div class="icon" style="background:#ecfdf5;color:var(--success);">&#x1f4c8;</div>
                Evolución Mensual
            </div>
            <div class="chart-container tall"><canvas id="chartTimeline"></canvas></div>
        </div>
    </div>
</div>

<script>
const COLORS = {
    primary: '#3642b5',
    primaryLight: '#4a55c9',
    accent: '#92b2f5',
    accent2: '#7072e0',
    success: '#10b981',
    warning: '#f59e0b',
    danger: '#ef4444',
    purple: '#7c3aed',
    pink: '#db2777',
    palette: ['#3642b5','#7072e0','#92b2f5','#10b981','#f59e0b','#ef4444','#7c3aed','#db2777','#06b6d4','#84cc16']
};

let charts = {};

function fmt(num) {
    if (num == null || isNaN(num)) return '$0.00';
    return '$' + Number(num).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function fmtShort(num) {
    if (num >= 1000000) return '$' + (num/1000000).toFixed(1) + 'M';
    if (num >= 1000) return '$' + (num/1000).toFixed(1) + 'K';
    return '$' + num.toFixed(0);
}

function getBadgeClass(estado) {
    const lower = (estado || '').toLowerCase();
    if (lower.includes('pagad') || lower.includes('cobrad') || lower.includes('paid')) return 'badge-pagado';
    if (lower.includes('pendiente') || lower.includes('pending')) return 'badge-pendiente';
    return 'badge-default';
}

function destroyCharts() {
    Object.values(charts).forEach(c => c.destroy());
    charts = {};
}

// ─── Multi-Select Component ───
const multiSelects = {};
let debounceTimer = null;

function debounceLoadData() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => loadData(), 400);
}

function createMultiSelect(wrapperId, options) {
    const wrapper = document.getElementById(wrapperId);
    if (!wrapper) return;
    const key = wrapper.dataset.key;
    const selected = new Set();

    wrapper.innerHTML = `
        <div class="ms-trigger" tabindex="0">
            <span class="ms-text">Todos</span>
            <span class="ms-arrow">&#9662;</span>
        </div>
        <div class="ms-dropdown">
            <input class="ms-search" type="text" placeholder="Buscar...">
            <div class="ms-options"></div>
            <div class="ms-footer">
                <button class="ms-select-all">Seleccionar todos</button>
                <span class="ms-count"></span>
                <button class="ms-clear-btn">Limpiar</button>
            </div>
        </div>
    `;

    const trigger = wrapper.querySelector('.ms-trigger');
    const dropdown = wrapper.querySelector('.ms-dropdown');
    const searchInput = wrapper.querySelector('.ms-search');
    const optionsContainer = wrapper.querySelector('.ms-options');
    const countSpan = wrapper.querySelector('.ms-count');

    function renderOptions(filter = '') {
        const lower = filter.toLowerCase();
        optionsContainer.innerHTML = '';
        const filtered = options.filter(o => o.toLowerCase().includes(lower));
        filtered.forEach(opt => {
            const div = document.createElement('div');
            div.className = 'ms-option';
            div.innerHTML = `<input type="checkbox" ${selected.has(opt)?'checked':''}><span title="${opt}">${opt}</span>`;
            div.addEventListener('click', (e) => {
                e.stopPropagation();
                if (selected.has(opt)) selected.delete(opt); else selected.add(opt);
                div.querySelector('input').checked = selected.has(opt);
                updateTrigger();
                debounceLoadData();
            });
            optionsContainer.appendChild(div);
        });
        countSpan.textContent = filtered.length + ' items';
    }

    function updateTrigger() {
        const text = wrapper.querySelector('.ms-text');
        const oldBadge = trigger.querySelector('.ms-badge');
        if (oldBadge) oldBadge.remove();
        if (selected.size === 0) {
            text.textContent = 'Todos';
        } else if (selected.size === 1) {
            const val = [...selected][0];
            text.textContent = val.length > 20 ? val.substring(0,18)+'...' : val;
        } else {
            text.textContent = [...selected].slice(0,2).map(v => v.length > 12 ? v.substring(0,10)+'..' : v).join(', ');
            const badge = document.createElement('span');
            badge.className = 'ms-badge';
            badge.textContent = selected.size;
            trigger.insertBefore(badge, trigger.querySelector('.ms-arrow'));
        }
    }

    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        document.querySelectorAll('.ms-dropdown.open').forEach(d => { if(d !== dropdown) d.classList.remove('open'); });
        document.querySelectorAll('.ms-trigger.active').forEach(t => { if(t !== trigger) t.classList.remove('active'); });
        dropdown.classList.toggle('open');
        trigger.classList.toggle('active');
        if (dropdown.classList.contains('open')) { searchInput.value = ''; renderOptions(); searchInput.focus(); }
    });

    searchInput.addEventListener('input', () => renderOptions(searchInput.value));
    searchInput.addEventListener('click', e => e.stopPropagation());

    wrapper.querySelector('.ms-select-all').addEventListener('click', (e) => {
        e.stopPropagation();
        const lower = searchInput.value.toLowerCase();
        options.filter(o => o.toLowerCase().includes(lower)).forEach(o => selected.add(o));
        renderOptions(searchInput.value);
        updateTrigger();
        debounceLoadData();
    });

    wrapper.querySelector('.ms-clear-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        selected.clear();
        renderOptions(searchInput.value);
        updateTrigger();
        debounceLoadData();
    });

    renderOptions();

    multiSelects[key] = {
        getSelected: () => [...selected],
        clear: () => { selected.clear(); updateTrigger(); renderOptions(); },
        setOptions: (newOpts) => { options = newOpts; renderOptions(); }
    };
}

// Close dropdowns on outside click
document.addEventListener('click', () => {
    document.querySelectorAll('.ms-dropdown.open').forEach(d => d.classList.remove('open'));
    document.querySelectorAll('.ms-trigger.active').forEach(t => t.classList.remove('active'));
});

function getFilters() {
    const f = {
        inicio_desde: document.getElementById('filterDesde').value,
        inicio_hasta: document.getElementById('filterHasta').value,
    };
    ['producer','razon_social','aseguradora','ejecutivo','estado_pago'].forEach(key => {
        if (multiSelects[key]) {
            const sel = multiSelects[key].getSelected();
            if (sel.length > 0) f[key] = sel.join('||');
        }
    });
    return f;
}

function clearFilters() {
    document.getElementById('filterDesde').value = '';
    document.getElementById('filterHasta').value = '';
    Object.values(multiSelects).forEach(ms => ms.clear());
    loadData();
}

async function loadFilters() {
    try {
        const resp = await fetch('/api/filters');
        const data = await resp.json();
        createMultiSelect('msProducer', data.producer || []);
        createMultiSelect('msRazonSocial', data.razon_social || []);
        createMultiSelect('msAseguradora', data.aseguradora || []);
        createMultiSelect('msEjecutivo', data.ejecutivo || []);
        createMultiSelect('msEstadoPago', data.estado_pago || []);
    } catch(e) { console.error('Error loading filters:', e); }
}

async function loadData() {
    document.getElementById('loadingOverlay').classList.remove('hidden');
    try {
        const filters = getFilters();
        const params = new URLSearchParams();
        Object.entries(filters).forEach(([k,v]) => { if(v) params.set(k,v); });
        const resp = await fetch('/api/dashboard?' + params.toString());
        const data = await resp.json();
        renderDashboard(data);
    } catch(e) {
        console.error('Error:', e);
        alert('Error al cargar datos: ' + e.message);
    } finally {
        document.getElementById('loadingOverlay').classList.add('hidden');
    }
}

function renderDashboard(data) {
    // KPIs
    const k = data.kpis || {};
    document.getElementById('kpiFeeNeto').textContent = fmt(k.total_fee_neto);
    document.getElementById('kpiMcProducer').textContent = fmt(k.total_mc_producer);
    document.getElementById('kpiMcZyra').textContent = fmt(k.total_mc_zyra);
    document.getElementById('kpiPrimaNeta').textContent = fmt(k.total_prima_neta);
    document.getElementById('kpiPolizas').textContent = (k.total_polizas || 0).toLocaleString();
    document.getElementById('recordCount').textContent = (data.total_records || 0).toLocaleString() + ' registros';
    const now = new Date();
    const timeStr = now.toLocaleTimeString('es-PE', {hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
    document.getElementById('lastUpdate').textContent = 'Actualizado: ' + timeStr;

    destroyCharts();

    // Helper for horizontal bar chart
    function hBar(canvasId, items, color) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        return new Chart(ctx, {
            type: 'bar',
            data: {
                labels: items.map(i => i.name.length > 30 ? i.name.substring(0,28)+'...' : i.name),
                datasets: [{
                    data: items.map(i => i.value),
                    backgroundColor: color + '20',
                    borderColor: color,
                    borderWidth: 1.5,
                    borderRadius: 4,
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: { label: ctx => fmt(ctx.parsed.x) }
                    }
                },
                scales: {
                    x: {
                        ticks: { callback: v => fmtShort(v) },
                        grid: { color: '#f0f0f0' }
                    },
                    y: {
                        ticks: { font: { size: 11 } },
                        grid: { display: false }
                    }
                }
            }
        });
    }

    // Top Contratantes Fee
    charts.contFee = hBar('chartContratantesFee', data.top_contratantes_fee || [], COLORS.primary);
    // Top Contratantes MC Producer
    charts.contMC = hBar('chartContratantesMcProducer', data.top_contratantes_mc_producer || [], COLORS.success);
    // Top Ramos Prima
    charts.ramosPrima = hBar('chartRamosPrima', data.top_ramos_prima || [], COLORS.warning);
    // Top Ramos MC Zyra
    charts.ramosMcZyra = hBar('chartRamosMcZyra', data.top_ramos_mc_zyra || [], COLORS.purple);

    // Estado de Pago Donut
    const epData = data.estado_pago || [];
    const ctxEP = document.getElementById('chartEstadoPago').getContext('2d');
    charts.estadoPago = new Chart(ctxEP, {
        type: 'doughnut',
        data: {
            labels: epData.map(e => e.estado),
            datasets: [{
                data: epData.map(e => e.prima_neta),
                backgroundColor: COLORS.palette.slice(0, epData.length),
                borderWidth: 2,
                borderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '60%',
            plugins: {
                legend: { position: 'bottom', labels: { font: { size: 11 }, padding: 12 } },
                tooltip: { callbacks: { label: ctx => ctx.label + ': ' + fmt(ctx.parsed) } }
            }
        }
    });

    // Estado Pago Table
    const tbody = document.querySelector('#estadoPagoTable tbody');
    tbody.innerHTML = '';
    epData.forEach(e => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><span class="estado-badge ${getBadgeClass(e.estado)}">${e.estado}</span></td>
            <td style="text-align:right;font-weight:600;">${e.count}</td>
            <td style="text-align:right;font-weight:600;">${fmt(e.prima_neta)}</td>
        `;
        tbody.appendChild(tr);
    });

    // Top Producers
    const prodData = data.top_producers || [];
    const ctxProd = document.getElementById('chartProducers').getContext('2d');
    charts.producers = new Chart(ctxProd, {
        type: 'bar',
        data: {
            labels: prodData.map(p => p.producer.length > 25 ? p.producer.substring(0,23)+'...' : p.producer),
            datasets: [{
                label: 'Fee Neto USD',
                data: prodData.map(p => p.fee_neto),
                backgroundColor: COLORS.primary + '30',
                borderColor: COLORS.primary,
                borderWidth: 1.5,
                borderRadius: 4,
            },{
                label: 'Comisión Producer USD',
                data: prodData.map(p => p.mc_producer),
                backgroundColor: COLORS.accent2 + '30',
                borderColor: COLORS.accent2,
                borderWidth: 1.5,
                borderRadius: 4,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top', labels: { font: { size: 11 } } },
                tooltip: { callbacks: { label: ctx => ctx.dataset.label + ': ' + fmt(ctx.parsed.x) } }
            },
            scales: {
                x: { ticks: { callback: v => fmtShort(v) }, grid: { color: '#f0f0f0' } },
                y: { ticks: { font: { size: 11 } }, grid: { display: false } }
            }
        }
    });

    // Timeline
    const tlData = data.timeline || [];
    const ctxTL = document.getElementById('chartTimeline').getContext('2d');
    charts.timeline = new Chart(ctxTL, {
        type: 'line',
        data: {
            labels: tlData.map(t => t.month),
            datasets: [{
                label: 'Prima Neta USD',
                data: tlData.map(t => t.prima_neta),
                borderColor: COLORS.primary,
                backgroundColor: COLORS.primary + '15',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 6,
                borderWidth: 2,
            },{
                label: 'Fee Neto USD',
                data: tlData.map(t => t.fee_neto),
                borderColor: COLORS.success,
                backgroundColor: COLORS.success + '15',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 6,
                borderWidth: 2,
            },{
                label: 'Comisión Zyra USD',
                data: tlData.map(t => t.mc_zyra),
                borderColor: COLORS.accent2,
                backgroundColor: COLORS.accent2 + '15',
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 6,
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: {
                legend: { position: 'top', labels: { font: { size: 12 }, usePointStyle: true, padding: 20 } },
                tooltip: { callbacks: { label: ctx => ctx.dataset.label + ': ' + fmt(ctx.parsed.y) } }
            },
            scales: {
                x: { grid: { display: false }, ticks: { font: { size: 11 } } },
                y: { ticks: { callback: v => fmtShort(v) }, grid: { color: '#f0f0f0' } }
            }
        }
    });
}

// Load white logo for header
fetch('/api/logo-white').then(r => r.text()).then(svg => {
    document.getElementById('logoContainer').innerHTML = svg;
    const svgEl = document.getElementById('logoContainer').querySelector('svg');
    if (svgEl) { svgEl.style.height = '48px'; svgEl.style.width = 'auto'; }
});

// Load original logo for loading spinner
fetch('/api/logo').then(r => r.text()).then(svg => {
    const el = document.getElementById('loadingLogoSvg');
    if (el) {
        el.innerHTML = svg;
        const svgEl = el.querySelector('svg');
        if (svgEl) { svgEl.style.height = '80px'; svgEl.style.width = 'auto'; }
    }
});

// Auto-apply on date change
document.getElementById('filterDesde').addEventListener('change', debounceLoadData);
document.getElementById('filterHasta').addEventListener('change', debounceLoadData);

// Initialize
loadFilters().then(() => loadData());

// Auto-refresh every 5 minutes (300000 ms)
setInterval(() => {
    console.log('Auto-refresh triggered');
    loadData();
}, 300000);
</script>
</body>
</html>
'''


class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logging

    def send_json(self, data, status=200):
        body = json.dumps(data, default=json_serial).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_svg(self, svg):
        body = svg.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.send_html(DASHBOARD_HTML)

        elif path == "/api/logo":
            self.send_svg(LOGO_SVG)

        elif path == "/api/logo-white":
            self.send_svg(LOGO_SVG.replace('fill: #042644;', 'fill: #ffffff;'))

        elif path == "/api/filters":
            try:
                options = fetch_filter_options()
                self.send_json(options)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        elif path == "/api/dashboard":
            try:
                filters = {k: v[0] for k, v in query.items() if v and v[0]}
                data = fetch_all_data(filters if filters else None)
                dashboard = compute_dashboard(data)
                self.send_json(dashboard)
            except Exception as e:
                self.send_json({"error": str(e)}, 500)

        else:
            self.send_response(404)
            self.end_headers()


def main():
    # Test DB connection first
    print("\n" + "=" * 60)
    print("  Dashboard de Comisiones - Zyra Brokers")
    print("=" * 60)
    print(f"\n  Conectando a {DB_CONFIG['host']}...")

    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) as total FROM {TABLE}")
            result = cursor.fetchone()
            total = result["total"] if result else 0
        conn.close()
        print(f"  Conexión exitosa. {total} registros encontrados.")
    except Exception as e:
        print(f"\n  ERROR de conexión: {e}")
        print("  Verifica las credenciales y que el servidor sea accesible.")
        sys.exit(1)

    # Start server
    with socketserver.TCPServer(("0.0.0.0", PORT), DashboardHandler) as httpd:
        print(f"\n  Servidor iniciado en: http://localhost:{PORT}")
        print("  Presiona Ctrl+C para detener.\n")
        print("=" * 60 + "\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Servidor detenido.")


if __name__ == "__main__":
    main()
