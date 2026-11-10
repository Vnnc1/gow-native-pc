#include "menu_settings.h"
#include "runtime/gow_menu_live.h"
#include "runtime/gow_menu_settings.h"
#include <QCoreApplication>
#include <QTemporaryDir>
#include <cassert>
#include <thread>
#include <iostream>
int main(int argc,char **argv) {
 QCoreApplication app(argc,argv);QCoreApplication::setOrganizationName("gow-menu-test");QCoreApplication::setApplicationName("isolated");
 QTemporaryDir temp;assert(temp.isValid());QSettings::setDefaultFormat(QSettings::IniFormat);QSettings::setPath(QSettings::IniFormat,QSettings::UserScope,temp.path());
 auto root=temp.path()+"/events";assert(QDir().mkpath(root+"/session"));qputenv("GOW_MENU_SETTINGS",(root+"/session").toUtf8());
 QSettings initial;initial.setValue("ajustes/idioma","pt");initial.sync();
 assert(gow_menu_settings::publish("\"fxaa\":false,\"audioVolume\":65,\"teclas\":{\"li_arriba\":[87]}"));
 auto changes=MenuSettings::consume(root);assert(changes.size()==3 && !changes["fxaa"].toBool());
 assert(MenuSettings::consume(root).isEmpty());
 assert(gow_menu_settings::publish("\"audioVolume\":25"));assert(MenuSettings::consume(root)["audioVolume"].toInt()==25);
 QSettings final;assert(final.value("ajustes/audioVolume").toInt()==25);assert(final.value("ajustes/idioma")=="pt");
 assert(MenuSettings::validate({{"fxaa",true},{"unknown",true}}).isEmpty());
 assert(MenuSettings::validate({{"audioVolume",101}}).isEmpty());
 assert(!MenuSettings::validate({{"teclas",QJsonObject{{"_modifierAliases",false},{"circle",QJsonArray{}}}}}).isEmpty());
 assert(MenuSettings::validate({{"teclas",QJsonObject{{"circle",QJsonArray{9000}}}}}).isEmpty());
 assert(MenuSettings::validate({{"mando",QJsonObject{{"circle",QJsonArray{14}}}}}).isEmpty());
 std::atomic<bool> stop{false};std::mutex mutex;std::condition_variable cv;
 for(bool shutdown:{false,true}) {
  gow_menu_live::pauseRequested=true;stop=false;std::chrono::steady_clock::duration duration{};
  std::thread guest([&]{duration=gow_menu_live::pauseAtBoundary(stop,mutex,cv);});
  const auto until=std::chrono::steady_clock::now()+std::chrono::seconds(2);
  while(!gow_menu_live::paused && std::chrono::steady_clock::now()<until) std::this_thread::yield();
  assert(gow_menu_live::paused);std::this_thread::sleep_for(std::chrono::milliseconds(30));
  assert(gow_menu_live::paused);if(shutdown)stop=true;else gow_menu_live::pauseRequested=false;cv.notify_all();guest.join();
  assert(!gow_menu_live::paused && duration>=std::chrono::milliseconds(30));
 }
 gow_menu_live::pauseRequested=false;
 int16_t audio[]={12000,-12000};gow_menu_live::volume=50;gow_menu_live::applyVolume(audio,2);assert(audio[0]==6000 && audio[1]==-6000);
 std::cout<<"PASS: durable settings, validation, isolation, pause/resume/shutdown, volume\n";
}
