#pragma once
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QSettings>
#include <QVariantMap>
#include <cmath>
#include <algorithm>
namespace MenuSettings {
inline QVariantMap validate(const QJsonObject &o) {
    QVariantMap result;
    for(auto it=o.begin();it!=o.end();++it) {
        const auto k=it.key(); const auto v=it.value(); bool valid=false;
        if(QStringList{"fxaa","vsync","mostrarFps","estirar","qteAuto","audioMute"}.contains(k)) valid=v.isBool();
        else if(k=="nitidez") valid=v.isDouble() && std::isfinite(v.toDouble()) && v.toDouble()>=0 && v.toDouble()<=1;
        else if(k=="audioVolume") valid=v.isDouble() && v.toInt(-1)>=0 && v.toInt(-1)<=100 && v.toDouble()==v.toInt();
        else if(k=="fpsLimite") valid=v.isDouble() && QList<int>{0,30,60,120,144,165,240}.contains(v.toInt(-1)) && v.toDouble()==v.toInt();
        else if(k=="filtro") valid=v.isString() && QStringList{"bilineal","fsr"}.contains(v.toString());
        else if(k=="anisotropico") valid=v.isString() && QStringList{"1","2","4","8","16"}.contains(v.toString());
        else if(k=="trucos") {
            valid=v.isString() && v.toString().size()<256;
            for(const auto &id:v.toString().split(',',Qt::SkipEmptyParts))
                valid=valid && QStringList{"inmortal","un_golpe","magia","furia","orbes","mejoras","poderes","medidores","extras"}.contains(id);
        } else if((k=="teclas" || k=="mando") && v.isObject()) {
            const auto map=v.toObject(); valid=!map.isEmpty() && map.size()<=40;
            const QStringList actions={"square","triangle","circle","cross","l1","r1","l2","r2","l3","r3","up","down","left","right","start","select","artemisa","furia","poseidon","medusa","zeus","hades","li_arriba","li_abajo","li_izq","li_der","ld_arriba","ld_abajo","ld_izq","ld_der","ld_mod","qte_stick"};
            for(auto a=map.begin();a!=map.end();++a) {
                if(k=="teclas" && a.key()=="_modifierAliases") {valid=valid && a.value().isBool();continue;}
                valid=valid && actions.contains(a.key()) && a.value().isArray() && a.value().toArray().size()<=8;
                for(const auto code:a.value().toArray()) {
                    int n=code.toInt(-1);
                    valid=valid && code.isDouble() && code.toDouble()==n && (k=="mando" ? n>=1 && n<=17 && n!=14 : (n>=32 && n<=348)||(n>=1000 && n<=1006));
                }
            }
            if(valid) {result[k]=QString::fromUtf8(QJsonDocument(map).toJson(QJsonDocument::Compact));continue;}
        }
        if(!valid) return {}; // Reject the entire transaction, never partly apply a binding/reset.
        result[k]=v.toVariant();
    }
    return result;
}
inline QVariantMap consume(const QString &root) {
    QVariantMap changes;
    QSettings settings; settings.beginGroup("ajustes");
    const QDir dir(root);
    int count=0;
    for(const auto &session:dir.entryInfoList(QDir::Dirs|QDir::NoDotAndDotDot,QDir::Name)) {
        if(session.isSymLink()) continue;
        auto files=QDir(session.filePath()).entryInfoList({"*.json"},QDir::Files,QDir::Name);
        std::sort(files.begin(),files.end(),[](const auto &a,const auto &b){return a.baseName().toUInt()<b.baseName().toUInt();});
        for(const auto &entry:files) {
            if(++count>4096) return changes;
            bool numeric=false;entry.baseName().toUInt(&numeric);
            QFile file(entry.filePath());
            if(!numeric || entry.isSymLink() || entry.size()>32770 || !file.open(QIODevice::ReadOnly)) continue;
            const auto doc=QJsonDocument::fromJson(file.readAll());file.close();
            const auto values=doc.isObject()?validate(doc.object()):QVariantMap{};
            if(values.isEmpty()) continue;
            for(auto it=values.begin();it!=values.end();++it) settings.setValue(it.key(),it.value());
            settings.sync();
            if(settings.status()!=QSettings::NoError) return changes;
            for(auto it=values.begin();it!=values.end();++it) changes[it.key()]=it.value();
            QFile::remove(entry.filePath());
        }
    }
    return changes;
}
}
