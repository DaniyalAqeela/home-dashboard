// Loads the dashboard display QML. All screen logic lives in the QML (part of the
// updatable app), so this file should almost never change.
// Usage: dashboard-display <path/to/Main.qml> [server-url]
#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QUrl>

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    if (argc < 2)
        return 2;
    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty(
        "dashboardUrl", argc > 2 ? QString::fromLocal8Bit(argv[2]) : QStringLiteral("http://127.0.0.1"));
    engine.load(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
    if (engine.rootObjects().isEmpty())
        return 1;
    return app.exec();
}
