# Changelog

Todas las modificaciones importantes en este proyecto se documentarán en este archivo.

El formato sigue parcialmente la convención de [Keep a Changelog](https://keepachangelog.com/es/1.0.0/) y está basado en [Semantic Versioning](https://semver.org/lang/es/).

## [1.0.0] Alpha 2 - 2025-05-16
### Añadido
- Primera versión funcional de la integración personalizada para Home Assistant 2025.5.1
- Configuración mediante `config_flow` con validación inicial
- Instalación a través de HACS posible tras incluir `manifest.json`
- Estructura básica de integración compatible con el sistema de componentes personalizados

### Corregido
- Error `Invalid handler specified` al configurar la integración desde la UI (solución: validación del flujo de configuración)
- Inclusión del archivo `manifest.json` para evitar el error “No manifest.json file found”

---

## [0.1.0] Alpha 1 - 2025-05-16
### Añadido
- Inicio del repositorio con estructura estándar de integración (`__init__.py`, `manifest.json`, `config_flow.py`, etc.)
