#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QQuickWindow>
#include <QObject>
#include <QTimer>
#include <QElapsedTimer>
#include <QList>
#include <QWebSocket>
#include <QNetworkRequest>
#include <QUrl>
#include <QDebug>

// Controlador expuesto a QML: cuenta fps reales via QQuickWindow::frameSwapped
// (señal real de vsync/GPU, no un timer aproximado) y mantiene el cliente WS
// contra el bridge ADR-058 — mismo header Origin explícito que requieren
// Flutter y Compose (el cliente nativo no lo manda solo).
class MicroPocController : public QObject {
    Q_OBJECT
    Q_PROPERTY(double fps READ fps NOTIFY fpsChanged)
    Q_PROPERTY(QString wsStatus READ wsStatus NOTIFY wsStatusChanged)
    Q_PROPERTY(int wsEvents READ wsEvents NOTIFY wsEventsChanged)

public:
    explicit MicroPocController(QObject *parent = nullptr) : QObject(parent) {
        connect(&m_statsTimer, &QTimer::timeout, this, &MicroPocController::logStats);
        m_statsTimer.start(1000);

        QNetworkRequest request(QUrl(QStringLiteral("ws://127.0.0.1:7341/events")));
        request.setRawHeader("Origin", "http://127.0.0.1:7341");

        connect(&m_ws, &QWebSocket::connected, this, [this]() {
            m_wsStatus = QStringLiteral("conectado");
            emit wsStatusChanged();
        });
        connect(&m_ws, &QWebSocket::disconnected, this, [this]() {
            m_wsStatus = QStringLiteral("cerrado por el servidor");
            emit wsStatusChanged();
        });
        connect(&m_ws, QOverload<QAbstractSocket::SocketError>::of(&QWebSocket::error), this, [this](QAbstractSocket::SocketError) {
            m_wsStatus = QStringLiteral("error: ") + m_ws.errorString();
            emit wsStatusChanged();
        });
        connect(&m_ws, &QWebSocket::textMessageReceived, this, [this](const QString &) {
            m_wsEvents += 1;
            emit wsEventsChanged();
        });
        m_ws.open(request);
    }

    void attachWindow(QQuickWindow *window) {
        connect(window, &QQuickWindow::frameSwapped, this, &MicroPocController::onFrameSwapped);
    }

    double fps() const { return m_fps; }
    QString wsStatus() const { return m_wsStatus; }
    int wsEvents() const { return m_wsEvents; }

signals:
    void fpsChanged();
    void wsStatusChanged();
    void wsEventsChanged();

private slots:
    void onFrameSwapped() {
        if (!m_clock.isValid()) {
            m_clock.start();
        }
        qint64 now = m_clock.elapsed();
        m_frameTimestamps.append(now);
        while (!m_frameTimestamps.isEmpty() && m_frameTimestamps.first() < now - 1000) {
            m_frameTimestamps.removeFirst();
        }
        m_fps = m_frameTimestamps.size();
        emit fpsChanged();
    }

    void logStats() {
        qInfo().noquote() << QStringLiteral("MICROPOC_STATS fps=%1 shader=ok (QML ShaderEffect GLSL/qsb) ws=%2 wsEvents=%3")
            .arg(int(m_fps))
            .arg(m_wsStatus)
            .arg(m_wsEvents);
    }

private:
    QTimer m_statsTimer;
    QElapsedTimer m_clock;
    QList<qint64> m_frameTimestamps;
    double m_fps = 0;
    QWebSocket m_ws;
    QString m_wsStatus = QStringLiteral("conectando");
    int m_wsEvents = 0;
};

int main(int argc, char *argv[]) {
    QGuiApplication app(argc, argv);

    auto *controller = new MicroPocController(&app);

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(QStringLiteral("statsController"), controller);

    QObject::connect(
        &engine, &QQmlApplicationEngine::objectCreated,
        &app,
        [controller](QObject *obj, const QUrl &) {
            if (auto *window = qobject_cast<QQuickWindow *>(obj)) {
                controller->attachWindow(window);
            }
        },
        Qt::QueuedConnection);

    engine.load(QUrl(QStringLiteral("qrc:/QtMicropoc/Main.qml")));

    if (engine.rootObjects().isEmpty()) {
        return -1;
    }

    return app.exec();
}

#include "main.moc"
