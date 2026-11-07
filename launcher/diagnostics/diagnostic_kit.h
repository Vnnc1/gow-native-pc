#pragma once
#include <QObject>
#include <QJsonObject>
#include <QTimer>

class DiagnosticKit : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString gamePath READ gamePath NOTIFY changed)
    Q_PROPERTY(QString statusKey READ statusKey NOTIFY changed)
    Q_PROPERTY(QString detail READ detail NOTIFY changed)
    Q_PROPERTY(QString report READ report NOTIFY changed)
    Q_PROPERTY(QString elfName READ elfName CONSTANT)
    Q_PROPERTY(bool running READ running NOTIFY changed)
public:
    explicit DiagnosticKit(QObject *parent = nullptr);
    QString gamePath() const { return m_game; }
    QString statusKey() const { return m_status; }
    QString detail() const { return m_detail; }
    QString report() const { return m_report; }
    QString elfName() const { return m_manifest.value("executable").toObject().value("name").toString(); }
    bool running() const { return m_running; }
    Q_INVOKABLE void chooseGame(const QString &title);
    Q_INVOKABLE bool start(bool detailed, bool fastVu, int scale);
    Q_INVOKABLE void stop();
    Q_INVOKABLE void mark(const QString &note);
    Q_INVOKABLE void exportReport();
    Q_INVOKABLE void openReports();
    bool selectGame(const QString &path);
signals:
    void changed();
private:
    void refresh();
    bool fail(const QString &key, const QString &detail = {});
    QString m_root, m_base, m_game, m_session, m_status = "diagReady", m_detail, m_report;
    QJsonObject m_manifest;
    QTimer m_timer;
    bool m_running = false;
};
