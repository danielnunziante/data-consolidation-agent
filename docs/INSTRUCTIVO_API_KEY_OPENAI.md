# Cómo obtener tu API Key de OpenAI

Este instructivo es para configurar la lectura automática del PDF de **VICTORIA ART**
en el Consolidador de Cuentas Corrientes.

VICTORIA ART entrega su cuenta corriente como un **PDF escaneado** (una imagen, sin
texto). Para leerlo automáticamente, el programa usa la inteligencia artificial de
OpenAI. Para eso necesitás una **API Key**: una especie de contraseña que conecta el
programa con tu cuenta de OpenAI.

> 💡 Es un trámite que se hace **una sola vez**. Después la pegás en el programa y listo.
> El costo de leer las pocas filas de VICTORIA por mes es de centavos de dólar.

---

## Paso 1 — Crear (o iniciar sesión en) tu cuenta de OpenAI

1. Entrá a 👉 **https://platform.openai.com/**
2. Si **no tenés cuenta**, hacé clic en **"Sign up"** y registrate con tu email
   (o con tu cuenta de Google/Microsoft).
3. Si **ya tenés cuenta**, hacé clic en **"Log in"** e ingresá.

---

## Paso 2 — Cargar saldo (billing)

La lectura por IA tiene un costo (muy bajo), así que primero hay que cargar un saldo
mínimo. Sin esto, la API key no funciona.

1. Una vez dentro, entrá a 👉 **https://platform.openai.com/settings/organization/billing**
   (o desde el menú: **Settings → Billing**).
2. Hacé clic en **"Add payment details"** / **"Add payment method"**.
3. Cargá una **tarjeta de crédito o débito** internacional.
4. Agregá un saldo inicial (por ejemplo **5 o 10 dólares**). Alcanza para muchísimos meses.

> 💡 Tip: en esa misma pantalla podés desactivar la recarga automática ("auto-recharge")
> si preferís controlar el gasto vos mismo.

---

## Paso 3 — Crear la API Key

1. Entrá a 👉 **https://platform.openai.com/api-keys**
   (o desde el menú: **API keys**).
2. Hacé clic en el botón **"+ Create new secret key"**.
3. Ponele un nombre que recuerdes, por ejemplo: **`Consolidador Coberser`**.
4. Hacé clic en **"Create secret key"**.

---

## Paso 4 — Copiar y guardar la API Key ⚠️ IMPORTANTE

1. Va a aparecer un texto largo que empieza con **`sk-...`**. Esa es tu API Key.
2. Hacé clic en **"Copy"** para copiarla.
3. **Pegala en un lugar seguro** (por ejemplo, un Bloc de notas o un gestor de
   contraseñas).

> ⚠️ **OpenAI te muestra la clave UNA SOLA VEZ.** Si cerrás esa ventana sin copiarla,
> no la vas a poder volver a ver y vas a tener que crear una nueva. No pasa nada grave:
> simplemente repetís el Paso 3.

> 🔒 **Tratá la API Key como una contraseña.** No la compartas por mail, chat ni
> capturas de pantalla. Quien la tenga puede gastar saldo de tu cuenta.

---

## Paso 5 — Cargarla en el programa

1. Abrí el **Consolidador de Cuentas Corrientes**.
2. En el panel de la izquierda, buscá la sección **"5 · OCR PDF ESCANEADO (OPCIONAL)"**.
3. **Pegá** tu API Key en el campo de texto (se muestra como puntitos •••• por seguridad).
4. Procesá normalmente. El programa guarda la clave en tu computadora, así que solo
   tenés que pegarla **la primera vez**.

¡Listo! A partir de ahora, las filas de VICTORIA ART se leen automáticamente.

---

## Preguntas frecuentes

**¿Cuánto cuesta?**
Centavos por mes. VICTORIA tiene apenas unas pocas filas, y cada lectura consume muy
poco. Con 5 dólares de saldo te alcanza para años.

**¿Es obligatorio?**
No. Si dejás el campo vacío, el programa funciona igual con todas las demás compañías;
solo las filas de VICTORIA ART quedarán sin cargar y las podés ingresar a mano.

**Me aparece un error de "quota" o "billing".**
Significa que falta cargar saldo (Paso 2) o que se agotó. Entrá a Billing y agregá saldo.

**¿Puedo cambiar la clave más adelante?**
Sí. Creá una nueva (Paso 3), pegala en el programa, y borrá la vieja desde
https://platform.openai.com/api-keys.
