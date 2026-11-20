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
| Número de versión | V2.2.105 |
| Número de serie | Ver `secrets/device.md` (no se publica) |

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

## Protocolo Xiaomi (verificado desde el PC con `src/xiaomi_client.py`)

| Campo | Valor |
|---|---|
| Transporte | Bluetooth Clásico, RFCOMM canal 2 (SPP) |
| Versión SPP | `02 00 5f` → protocolo SPP **v2** (tramas `A5 A5`, CRC-16/ARC) |
| Sesión del reloj | máx. paquete `0x8000` (32768 B), ventana TX 3, timeout 16000 ms |
| Autenticación | nonces + HKDF-SHA256 (`"miwear-auth"`) + HMAC; clave de Mi Fitness (`secrets/auth_key.txt`) |
| Cifrado tras auth | AES-128-CTR (la propia clave como IV); info del teléfono con AES-CCM (tag 4 B) |
| Capacidades (auth step 4) | `device_capability=52851550`, `device_capability_2=16885157` |
| Emparejamiento PC | Directo por MAC (`src/pair_watch.py --direct`), sin resetear: la clave sigue siendo válida |

## Datos leídos del reloj (2026-11-16)

| Campo | Valor |
|---|---|
| Modelo (protocolo) | M2351W1 |
| Modelo Mi Fitness | `lchz.watch.n65agl` (did: ver `secrets/device.md`) |
| Número de serie | Ver `secrets/device.md` (no se publica) |
| Firmware | **2.2.110** (la pantalla mostraba 2.2.105; probablemente se actualizó al vincular con Mi Fitness) |
| Batería | 86 %, cargando |
| Última carga registrada | 2026-11-16 17:35:34 CET |

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

