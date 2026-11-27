# Instalarea și utilizarea extensiei EC Quote Asistent WhatsApp

Acest ghid este destinat colegilor din echipa Etichete Creative care răspund clienților pe WhatsApp Web. Extensia afișează sugestii de răspuns și oferte calculate de server, dar nu trimite niciodată mesaje singură: dvs. verificați textul sau imaginea și apăsați Trimite.

## 1. Instalarea din Chrome Web Store (varianta obișnuită, cu actualizări automate)

1. Conectați-vă în Google Chrome cu contul Google de serviciu aprobat de administrator.
2. Deschideți linkul privat al extensiei primit de la administrator (listare privată Chrome Web Store, vizibilă doar conturilor autorizate).
3. Apăsați butonul **Add to Chrome** (Adaugă în Chrome), apoi confirmați în fereastra afișată apăsând **Add extension**.
4. După instalare se deschide automat pagina **Opțiuni EC Quote**. Fixați iconița **EC** în bara de sus din Chrome (clic pe pictograma de puzzle din dreapta adresei, apoi pe pioneza din dreptul „EC Quote Asistent WhatsApp”).

## 2. Instalarea rapidă dintr-o arhivă ZIP (dezvoltare sau urgență când WhatsApp s-a schimbat)

Dacă o actualizare nu a trecut încă de verificarea din Chrome Web Store, administratorul vă trimite arhiva `ec-quote-extension-<versiune>.zip`:

1. Dezarhivați fișierul `.zip` într-un folder permanent de pe calculator (de exemplu `C:\EC-Quote-Extensie`). Nu ștergeți acest folder după instalare.
2. Deschideți în Chrome adresa `chrome://extensions`.
3. Activați comutatorul **Developer mode** (Modul pentru dezvoltatori) din colțul dreapta-sus.
4. Apăsați butonul **Load unpacked** (Încarcă extensie neîmpachetată) din stânga-sus și selectați folderul dezarhivat (cel care conține fișierul `manifest.json`).
5. Verificați că extensia apare activă în listă și că se deschide pagina de opțiuni.

## 3. Configurarea adresei serverului și a tokenului personal

1. În pagina de opțiuni (sau clic pe iconița **EC** din bara Chrome), completați câmpul **Adresa serverului** cu adresa HTTPS comunicată de administrator (de exemplu `https://oferta.etichetecreative.ro`).
2. Lipiți în câmpul **Token personal** tokenul individual primit. După salvare, câmpul rămâne gol și afișează doar textul „Token salvat”.
3. Alegeți modul de lucru recomandat la început (**La cerere** sau **Automat**) și lăsați bifat **Asistent activ**.
4. Apăsați butonul **Testează conexiunea**.
5. Chrome va afișa o fereastră prin care cere permisiunea de a comunica cu adresa serverului configurat; apăsați **Allow** (Permite).
6. Sub butoane trebuie să apară mesajul verde: `Conexiune reușită. Operator: <numele dvs.>.`

## 4. Verificarea compatibilității pe WhatsApp Web (auto-test)

1. Deschideți `https://web.whatsapp.com` și faceți clic pe o conversație individuală cu un client.
2. În dreapta ferestrei apare panoul **Asistent ofertare**.
3. Priviți subsolul panoului: trebuie să scrie **Compatibilitate WhatsApp Web: ok** cu bulină verde.
4. Dacă scrie **Compatibilitate WhatsApp Web: de verificat** (iar pe iconița extensiei apare semnul `!`), faceți clic pe acel text din subsol: se deschide lista elementelor verificate (`ok` sau `negăsit`). Trimiteți captura sau lista administratorului și, până la actualizare, folosiți butonul **Copiază textul** sau răspundeți manual.

## 5. Oprirea temporară, actualizarea și dezinstalarea

- **Restrângerea panoului**: apăsați săgeata din dreapta-sus a panoului pentru a-l restrânge într-o bandă îngustă de 40 px.
- **Oprirea completă**: faceți clic pe iconița **EC** din bara Chrome, debifați **Asistent activ** și apăsați **Salvează**. Panoul dispare din WhatsApp Web, nu se mai citește nimic din pagină, iar pe iconiță apare `OPR`.
- **Actualizarea**:
  - dacă ați instalat din Chrome Web Store, actualizarea se face singură (sau din `chrome://extensions` apăsând **Update**);
  - dacă apare în panou mesajul **Actualizați extensia**, instalați noua versiune din magazin sau dezarhivați noul `.zip` peste folderul existent și apăsați pictograma de reîncărcare a extensiei în `chrome://extensions`.
- **Dezinstalarea**: deschideți `chrome://extensions`, căutați **EC Quote Asistent WhatsApp** și apăsați **Remove** (Elimină). Tokenul salvat local se șterge odată cu extensia.
