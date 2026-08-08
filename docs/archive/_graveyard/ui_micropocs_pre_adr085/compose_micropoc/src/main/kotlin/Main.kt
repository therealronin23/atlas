import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.graphics.asComposeShader
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import io.ktor.client.HttpClient
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.websocket.WebSockets
import io.ktor.client.plugins.websocket.webSocket
import io.ktor.client.request.header
import io.ktor.websocket.Frame
import java.nio.ByteBuffer
import java.nio.ByteOrder
import org.jetbrains.skia.Data
import org.jetbrains.skia.RuntimeEffect
import kotlin.math.cos
import kotlin.math.sin

private fun packUniforms(values: FloatArray): Data {
    val buffer = ByteBuffer.allocate(values.size * 4).order(ByteOrder.LITTLE_ENDIAN)
    values.forEach { buffer.putFloat(it) }
    return Data.makeFromBytes(buffer.array())
}

// Réplica del micro-PoC de referencia (glow + partículas orbitando, fps en
// vivo, cliente WS real contra el bridge de Atlas) — mismos criterios que
// prototypes/atlas_ui/flutter_micropoc/ para comparación directa por los
// mismos números.

private const val PARTICLE_COUNT = 24

private val glowEffect = RuntimeEffect.makeForShader(
    """
    uniform float2 uSize;
    uniform float uTime;

    half4 main(float2 fragCoord) {
        float2 center = uSize * 0.5;
        float2 p = fragCoord - center;
        float dist = length(p);
        float maxRadius = min(uSize.x, uSize.y) * 0.4;

        float ring1 = abs(dist - maxRadius * (0.5 + 0.1 * sin(uTime * 1.3)));
        float ring2 = abs(dist - maxRadius * (0.8 + 0.08 * sin(uTime * 1.7 + 1.0)));
        float ring3 = abs(dist - maxRadius * (0.65 + 0.12 * sin(uTime * 2.1 + 2.3)));

        float glow1 = smoothstep(24.0, 0.0, ring1);
        float glow2 = smoothstep(18.0, 0.0, ring2);
        float glow3 = smoothstep(20.0, 0.0, ring3);

        float w1 = glow1 * 0.8;
        float w2 = glow2 * 0.5;
        float w3 = glow3 * 0.45;
        float wSum = w1 + w2 + w3;

        half3 cyan = half3(0.0, 0.85, 1.0);
        half3 violet = half3(0.6, 0.2, 1.0);
        half3 mixColor = wSum > 0.0 ? (cyan * (w1 + w2) + violet * w3) / wSum : half3(0.0);

        float alpha = clamp(wSum, 0.0, 1.0);
        return half4(mixColor * alpha, alpha);
    }
    """.trimIndent()
)

private class WsStatus {
    var text: String = "conectando"
    var eventsReceived: Int = 0
}

fun main() = application {
    Window(onCloseRequest = ::exitApplication, title = "Atlas micro-PoC (Compose Desktop)") {
        MicroPocScreen()
    }
}

@Composable
private fun MicroPocScreen() {
    var fps by remember { mutableStateOf(0.0) }
    val wsStatus = remember { WsStatus() }
    var wsStatusText by remember { mutableStateOf(wsStatus.text) }
    var wsEvents by remember { mutableStateOf(0) }

    val infiniteTransition = rememberInfiniteTransition(label = "orbit")
    val angle by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = (2 * Math.PI).toFloat(),
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 8000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "angle",
    )
    val time by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1000f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 1_000_000, easing = LinearEasing),
            repeatMode = RepeatMode.Restart,
        ),
        label = "time",
    )

    // Contador de fps: media móvil sobre el último segundo real (mismo
    // método que el micro-PoC Flutter: /proc RSS aparte, aquí solo frames).
    val frameTimestamps = remember { mutableListOf<Long>() }
    LaunchedEffect(Unit) {
        while (true) {
            withFrameNanos { nowNanos ->
                val nowMs = nowNanos / 1_000_000
                frameTimestamps.add(nowMs)
                while (frameTimestamps.isNotEmpty() && frameTimestamps.first() < nowMs - 1000) {
                    frameTimestamps.removeAt(0)
                }
                fps = frameTimestamps.size.toDouble()
            }
        }
    }

    // Cliente WS real contra el bridge ADR-058 — igual que Flutter, con el
    // header Origin explícito porque el cliente nativo no lo manda solo.
    LaunchedEffect(Unit) {
        val client = HttpClient(CIO) { install(WebSockets) }
        try {
            client.webSocket(
                host = "127.0.0.1",
                port = 7341,
                path = "/events",
                request = { header("Origin", "http://127.0.0.1:7341") },
            ) {
                wsStatus.text = "conectado"
                wsStatusText = wsStatus.text
                for (frame in incoming) {
                    if (frame is Frame.Text) {
                        wsStatus.eventsReceived += 1
                        wsEvents = wsStatus.eventsReceived
                    }
                }
                wsStatus.text = "cerrado por el servidor"
                wsStatusText = wsStatus.text
            }
        } catch (e: Exception) {
            wsStatus.text = "error: ${e.message}"
            wsStatusText = wsStatus.text
        }
    }

    // Log periódico a stdout — mismo formato MICROPOC_STATS que Flutter
    // para comparar directamente sin parsear dos formatos distintos.
    LaunchedEffect(Unit) {
        while (true) {
            kotlinx.coroutines.delay(1000)
            println(
                "MICROPOC_STATS fps=${fps.toInt()} shader=ok (Skia RuntimeEffect SkSL) " +
                    "ws=$wsStatusText wsEvents=$wsEvents",
            )
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val shader = glowEffect.makeShader(
                packUniforms(floatArrayOf(size.width, size.height, time)),
                null,
                null,
            )
            drawRect(brush = ShaderBrush(shader.asComposeShader()))

            val center = Offset(size.width / 2f, size.height / 2f)
            val orbitRadius = minOf(size.width, size.height) * 0.32f
            repeat(PARTICLE_COUNT) { i ->
                val particleAngle = angle + i * (2 * Math.PI.toFloat() / PARTICLE_COUNT)
                val x = center.x + orbitRadius * cos(particleAngle)
                val y = center.y + orbitRadius * sin(particleAngle)
                drawCircle(
                    color = Color(0xFF00D9FF),
                    radius = 4f,
                    center = Offset(x, y),
                )
            }
        }

        Column(modifier = Modifier.align(Alignment.TopStart).padding(16.dp)) {
            Text("fps: ${fps.toInt()}", color = Color.White, style = MaterialTheme.typography.bodyLarge)
            Text("ws: $wsStatusText  events: $wsEvents", color = Color.White, style = MaterialTheme.typography.bodySmall)
        }
    }
}
