# Redmi Watch 5 Active: Acerca de

## Información del dispositivo

| Campo | Valor |
|---|---|
| Nombre | Redmi Watch 5 Active |
| Modelo | M2351W1 |
| Dirección MAC | Ver `secrets/device.md` (no se publica) |

## Sistema

| Campo | Valor |
|---|---|
| Watch OS | Xiaomi HyperOS |
| Número de versión | **2.2.111** (leído por protocolo, `2/2`, 2026-11-24). Historial: 2.2.105 en pantalla al estrenarlo → 2.2.110 (2026-11-16, tras vincular con Mi Fitness) → 2.2.111 (instalado por Mi Fitness el 2026-11-22) |
| Número de serie | Ver `secrets/device.md` (no se publica) |
| Motor OTA | `ota_type = 2` (Mi Fitness, etiqueta `CheckUpdate`, 2026-11-22): actualización general por el canal mass, no por el canal 6 |
| SoC | SiFli SF32LB5x, doble núcleo Cortex-M33: HCPU (aplicación RT-Thread) + LCPU (pila Bluetooth/SPP). Deducido del paquete 2.2.111 (análisis estático, `docs/firmware.md`); SKU exacto sin confirmar |

## Bluetooth (obtenido desde el PC)

| Campo | Valor |
|---|---|
| Nombre Bluetooth | Redmi Watch 5 Active (+ sufijo de la MAC, ver `secrets/device.md`) |
| Tipo de dirección | Pública |
| Modo | Dual (Bluetooth Clásico + BLE) |
| Clase de dispositivo | `0x280704`: Wearable / Reloj de pulsera (servicios: Audio, Telefonía) |
| Chip / pila Bluetooth | SiFli (proveedor en los registros SDP) |
| PnP / Modalias | `bluetooth:v0AC4pB009d011B` (vendor `0x0AC4`, producto `0xB009`, versión `0x011B`) |
| Emparejamiento | Secure Simple Pairing, comparación numérica (no legacy) |
| Visible para otros | Solo en modo "Conectar teléfono nuevo"; si está vinculado no anuncia |
| Revisión 2026-11-24 (2.2.111) | Clase, modalias (`d011B`) y los UUID que BlueZ tiene en caché no cambian. `sdptool` no sirvió para releer los registros: `browse` solo devolvió HID y PnP, y `records` agotó el tiempo de espera. La tabla de servicios es la de 2.2.110 |

### Servicios (SDP)

| Servicio | UUID | Transporte | Uso probable |
|---|---|---|---|
| BTS2 SPPA (Serial Port) | `0x1101` | RFCOMM canal 2 | Protocolo propietario Xiaomi (datos, sincronización) |
| Hands-Free unit | `0x111E` v1.8 | RFCOMM canal 3 | Llamadas Bluetooth desde el reloj |
| Advanced Audio (A2DP Source) | `0x110A` v1.4 | L2CAP PSM 25 | Audio del reloj |
| AV Remote Controller | `0x110E`/`0x110F` v1.6 | L2CAP PSM 23 | Control multimedia del teléfono |
| AV Remote Target | `0x110E`/`0x110C` v1.6 | L2CAP PSM 23 | Control multimedia |
| HID remote control | `0x1124` | L2CAP PSM 17 | Mando remoto (p. ej. obturador de cámara) |
| PnP Information | `0x1200` | SDP | Identificación del dispositivo |
| Xiaomi Inc. (GATT sobre BR/EDR) | `0xFDAB` | ATT, handles `0x0028`–`0x0030` | Servicio propietario Xiaomi |
| Desconocido (GATT sobre BR/EDR) | `0x3802` | ATT, handles `0x0031`–`0x0034` | Servicio propietario |

### Notas

- En la zona puede haber otros relojes del mismo modelo. Las direcciones y los números de
  serie locales están en `secrets/device.md` (no se publican).

## Protocol Xiaomi (verificado desde el PC con `src/xiaomi_client.py`)

| Campo | Valor |
|---|---|
| Transporte | Bluetooth Clásico, RFCOMM canal 2 (SPP) |
| Versión SPP | `02 00 5f` → protocolo SPP **v2** (tramas `A5 A5`, CRC-16/ARC) |
| Sesión del reloj | máx. paquete `0x8000` (32768 B), ventana TX 3, timeout 16000 ms |
| Autenticación | nonces + HKDF-SHA256 (`"miwear-auth"`) + HMAC; clave de Mi Fitness (`secrets/auth_key.txt`) |
| Cifrado tras auth | AES-128-CTR (la propia clave como IV); info del teléfono con AES-CCM (tag 4 B) |
| Capacidades (auth step 4) | `device_capability=52851550`, `device_capability_2` variable |
| Emparejamiento PC | Directo por MAC (`src/pair_watch.py --direct`), sin resetear: la clave sigue siendo válida |

### Comandos probados (firmware 2.2.110, modelo limitado)

Revisado en **2.2.111** el 2026-11-24, solo con lecturas: `2/1`, `2/2`, `2/14` (settings 1 y 2),
`2/24`, `2/51`, `4/0`, `8/2` y `8/29` responden igual que en 2.2.110, y `2/34` y `2/78` siguen
devolviendo `status: 1`. Las escrituras de la tabla no se repitieron en 2.2.111.

| Comando | Resultado |
|---|---|
| `--send 2 1` (battery) | ✓ — `level: 100, state: 3` |
| `--send 2 2` (device info) | ✓ — serial, firmware, model |
| `--send 2 14 --payload 'system { miscSettingGet { setting: 2 } }'` | ✓ — dndSync y ajustes de notificación |
| `--send 2 14 --payload 'system { miscSettingGet { setting: 1 } }'` | ✓ — `wakeScreen/onlyWhenPhoneLocked/onlyWhenWorn` |
| `--send 2 15 --payload 'system { miscSettingSet { dndSync { enabled: 1 } } }'` | ✓ — `status: 0`; lectura posterior `enabled: 1` |
| `--send 2 15 --payload 'system { miscSettingSet { miscNotificationSettings { wakeScreen: 1 onlyWhenPhoneLocked: 2 onlyWhenWorn: 2 } } }'` | ✓ — `status: 0`; lectura posterior coincide |
| `--send 2 18 --payload 'system { findDevice: 0 }' --listen 8` (find-device) | ✓ — `status: 0`, el reloj suena; al terminar envía `system { findDevice: 1 }`. Sin payload ni `--listen` (desconexión inmediata) respondió `status: 0` pero no sonó (2026-11-22) |
| `--send 2 23` / `2 34` (DND) | ✗ — `status: 1` (no implementado) |
| `--send 2 24` (raiseToWake get) | ✓ — `mode: 2 start 8:00 end 22:00` |
| `--send 2 25` (raiseToWake set) | ✗ — ACK de transporte, sin respuesta; el valor no cambia |
| `--send 2 39` (workoutTypes) | ✓ — 100+ tipos |
| `--send 2 51` (widgetScreens) | ✓ — 4 pantallas |
| `--send 2 53` (widgetParts) | ✓ — 80+ partes |
| `--send 2 78` / `2 79` (deviceState) | ✗ — `status: 1` |
| `--send 4 0` (watchface list) | ✓ — 4 esferas: Swirl (activa), Dynamic data, Step space, Twilight |
| `--send 4 1` (watchface set) | ACK — `ack: 1`, no es la lista |
| `--send 4 4` (install status) | ✓ — `watchface {}` vacío |
| `--send 8 8` (2.2.111) | ✓ — ajustes de SpO2: `allDayCapable: 1 mode: SPO2_MODE_OFF`, alarma baja desactivada (umbral 80) |
| `--send 8 12` (2.2.111) | ✓ — `standingReminder { enabled: true dnd: true }`, pero las horas salen fuera de rango (`start 14:96`, `dndEnd 160:30`): el proto probablemente no encaja con lo que envía este firmware |
| `--send 8 35` (2.2.111) | ✓ — `vitalityScore { sevenDay: false dailyProgress: false }` |
| `--send 8 42` (goals get, 2.2.111) | ✓ — `currentGoals: 1,2,3`, `supportedGoals: 1,2,3,4` |

El reloj es un modelo de firmware limitado: las escrituras de DND (2/23, 2/34),
raiseToWake (2/25) y deviceState (2/78, 2/79) no están implementadas. DND se probó de
forma exhaustiva: 2/23 con status 0 y 2, y 2/34 con status 0, todos devuelven
`status: 1` y no cambian ni 2/34 ni la lectura de 2/14 setting 2 (`dndSync.enabled: 0`).
La ruta de escritura quedó verificada con dos ajustes persistentes:

- **dndSync**: lectura `enabled: 0` → escritura `enabled: 1` (`status: 0`) → lectura en
  sesión nueva `enabled: 1` → restauración `enabled: 0` → lectura `enabled: 0`.
- **Notificaciones**: `wakeScreen 2→1`, `onlyWhenPhoneLocked 1→2`, `onlyWhenWorn 1→2`,
  lectura en sesión nueva, y restauración a `2/1/1`.

Las cadenas de payload y las restricciones están en `docs/protocol.md` (sección
"Hardware verification") y fijadas por tests de `build_command()`.

## Sesión SPP, captura y canales sin decodificar (2026-11-20)

| Hecho | Detalle |
|---|---|
| Duración de la sesión | El reloj cierra el enlace ~20–26 s después de la autenticación, con o sin tráfico (reinicios medidos a 22,7 / 23,0 / 25,5 / 25,7 s). Un `--keepalive` cada 3 s mantiene el diálogo pero **no** alarga la sesión |
| Reconexión tras un corte | Los primeros intentos fallan con `EHOSTDOWN` (errno 112); un reintento ~10 s después conecta |
| Latido en reposo | `18/0` (tipo Music vacío) cada ~1 s cuando el enlace está inactivo; desaparece si hay otra actividad |
| Datos de salud en vivo | `8/45` no responde directamente pero arranca una ráfaga `8/47` `realTimeStats { steps calories heartRate }` cada ~1 s, **por el canal 1** |
| Entrenamiento en curso | Cuatro sesiones con sentadillas: 114 frames, todos por el canal 1; 74 muestras de pulso de 0 a 112 ppm; `steps`/`calories` a 0 |
| Tras guardar el entrenamiento | `8/2` sigue devolviendo `activityRequestFileIds: ""`, también con `activitySyncRequestToday { unknown1: 1 }` |
| Sincronización de actividad | `8/2` devuelve `activityRequestFileIds: ""` (sin ficheros en cola): apunta a una transferencia por ficheros |
| `8/3` (actividad pasada) | Sin respuesta |
| `8/8`, `8/12`, `8/35` | Responden con datos |
| Canales 2 y 5 | **Ningún frame** en ninguna de las cinco sesiones capturadas |
| `OP_READ` en el canal 2 (2026-11-23, 2.2.111) | `Command{0,0}` (`08001000`) con opcode 3: ACK de L1, ningún DATA en el canal 2 y ningún reinicio en 4 s |

### Revisión en 2.2.111 (2026-11-24)

| Hecho | Detalle |
|---|---|
| Duración de la sesión | 7 sesiones en reposo (`--listen 40`): 6 se cierran entre 22,1 y 22,4 s después de la autenticación; una se cerró a los 12,4 s. Es más estable que en 2.2.110, pero sigue sin depender del tráfico |
| Causa probable del corte | El FSM de login del LCPU espera el intercambio verify/confirm de Mi Fitness; su temporizador de 10 s vence dos veces y se libera la sesión (análisis estático, `docs/lcpu.md`) |
| Latido en reposo | **No aparece** el `18/0`: en las 7 sesiones, 3 de ellas con el reloj puesto, solo llegaron los dos frames de autenticación |
| Datos de salud en vivo | `8/45` sigue sin respuesta directa y arranca `8/47` cada ~1 s por el canal 1. Con el reloj puesto, `heartRate` está a 0 durante ~18 s y luego da 58–62 ppm; `steps`/`calories` a 0 |
| Capacidades (auth step 4) | `device_capability: 52851550` fijo; `device_capability_2` solo aparece en algunas sesiones y varía (p. ej. `20697`) |

La captura se hace con `src/xiaomi_client.py --capture` (NDJSON, ambos sentidos) y se
analiza en frío con `src/decode_capture.py`; el método y los resultados están en
`docs/channels.md`. Como la sesión dura ~25 s, las pruebas largas se hacen en ventanas y
con `--send` repetible.

## ARQ y tamaño de trama (2026-11-22)

| Hecho | Detalle |
|---|---|
| Ventana de envío | El reloj hace ACK acumulativo por seq de 8 bits. 300 comandos seguidos (cruce 255→0) drenan la ventana sin un solo reintento y con 300/300 respuestas |
| Ráfaga sin esperar respuesta | 40 comandos seguidos: el cliente deja de enviar al llegar a 32 sin ACK y reanuda al liberarse la ventana; 40/40 respuestas |
| Trama grande | 16 KB de payload por frame: 20 frames (320 KB) en ~3 s, 20/20 respuestas. Una trama de 24 KB cierra el enlace (límite práctico por debajo del MPS anunciado) |

## Datos leídos del reloj (2026-11-16)

| Campo | Valor |
|---|---|
| Modelo (protocolo) | M2351W1 |
| Modelo Mi Fitness | `lchz.watch.n65agl` (did: ver `secrets/device.md`) |
| Número de serie | Ver `secrets/device.md` (no se publica) |
| Firmware | **2.2.110** (la pantalla mostraba 2.2.105; probablemente se actualizó al vincular con Mi Fitness) |
| Batería | 86 %, cargando |
| Última carga registrada | 2026-11-16 17:35:34 CET |

Lectura del 2026-11-24: firmware **2.2.111**, batería `level: 95 state: 2`, última carga
registrada el 2026-11-20 16:29:42 CET (`timestampSeconds: 1795188582`), y las mismas 4 esferas
con Swirl activa.

## Audio HFP (verificado 2026-11-16 con `src/audio_test.py`)

| Hecho | Detalle |
|---|---|
| Perfiles expuestos | `headset-head-unit` (mSBC, 16 kHz) y `headset-head-unit-cvsd`; el reloj es el HF y el PC el AG |
| Nodos | `bluez_output.<mac>.1` (sink) y `bluez_input.<mac>.0` (source), ambos 16 kHz mono (la MAC va con guiones bajos; ver `secrets/device.md`) |
| Volumen por defecto del sink | 40 % (−23,88 dB); los tonos se oyen pero flojos |
| **Verificación real** | Contadores SCO de `hciconfig hci0`: si `sco_tx` no sube, **no salió audio** de la radio. Es la única prueba fiable; el código de salida y el tiempo de `paplay` no valen (medido: `rc=0` en 0,83 s con **0** paquetes) |
| **Transporte nuevo por stream** | Re-crear el transporte antes de cada reproducción (`pactl set-card-profile off` + `headset-head-unit`) da **6/6** con 215–248 paquetes por clip de 0,75 s. Reutilizarlo suele romperlo |
| Reproducir con una captura abierta | **Contraproducente**: con un `parecord` vivo, la reproducción envía **0** paquetes (0/4 y 0/3), aunque `paplay` salga con 0 en 0,85 s. El enlace SCO es uno solo y se lo queda la captura |
| Fallo al reproducir | El clip se entrega y el servidor lo "reproduce" contra un transporte muerto: `paplay` sale con 0 y no suena nada. Si el enlace se cae a mitad, el contador se queda corto (p. ej. 140 de ~230) y `wireplumber` registra `Failure in Bluetooth audio transport` |
| **Ventana de reproducción** | **~1,3 s** (≈380 paquetes): pasado ese tiempo el reloj cierra el SCO. Se ve en `hcitool con`, donde el enlace desaparece mientras el cliente sigue escribiendo. Clips de 2, 3 y 5 s fallan siempre a esa altura, con mSBC y con CVSD |
| Ventana de captura | No tiene ese límite: las tomas de 4 s funcionan |
| Búfer del cliente | No influye: `PULSE_LATENCY_MSEC` 10/20/50/100 y `pw-cat --latency` 20/50 ms fallan igual |
| Reproducción larga | `loopback` parte el audio en trozos de 0,7 s, cada uno con transporte nuevo; entre trozos queda un hueco audible que no se puede evitar |
| Fallo al capturar | `parecord` **no da error**: escribe silencio digital y sale con 0 (peak 0 %). Con el transporte re-creado, 4/4 tomas con señal |
| Transporte SCO muerto | Tras `Failure in Bluetooth audio transport` el objeto del transporte (`/org/bluez/…/fdNN`) sobrevive a los reinicios de WirePlumber; re-crear el perfil lo arregla, y `systemctl --user restart wireplumber` es el último recurso |
| Códec | Irrelevante: CVSD falla igual que mSBC |
| Cliente | Idéntico con `pw-play` y con `paplay`: no es cosa del shim de PulseAudio |
| Micrófono | Funciona (peak 26–71 % con música) cuando el enlace está arriba; no capta su propio altavoz (cancelación de eco), así que no sirve para verificar la reproducción |
| Captura | Pierde ~1 s inicial (establecimiento del SCO); `record()` graba `+1,5 s` y reintenta si la toma son todo ceros |
| Llamadas desde el móvil | Fiables: durante la llamada el enlace SCO ya está establecido |

Resumen: el reloj no rechaza el audio; lo que falla es el **transporte** SCO del PC, que no tolera
ser reutilizado y a veces queda en un estado en el que acepta PCM sin transmitir nada. Por eso
`src/audio_test.py` re-crea el perfil antes de cada stream y comprueba los contadores SCO en vez de
fiarse del cliente. Además el reloj cierra el enlace tras ~1,3 s de reproducción continua, así que
`loopback` reproduce en trozos de 0,7 s con un hueco entre ellos. Es un workaround: la causa de
fondo está en la pila BlueZ/WirePlumber + firmware del reloj, no en el protocolo Xiaomi.

