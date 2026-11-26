# Șabloane de mockup

Fiecare folder de aici este un șablon: `template.json` + `photo.jpg` (opțional `shade.png`, `mask.png`).
Cele 5 existente (`borcan`, `pahar-cafea`, `cutie`, `sticla`, `punga-kraft`) sunt PROVIZORII: desenate de
`python3 -m ec_quote.mockup.make_placeholders`, marcate `"placeholder": true` și cu textul
"SABLON PROVIZORIU" în colț. Se înlocuiesc cu fotografii reale.

## Cum adaugi un șablon real

1. Fotografia
   - Produsul fără etichetă, pe fundal neutru, lumină moale dintr-o parte, fără alte obiecte peste zona etichetei.
   - Orizontală 4:3, minimum 1600 px pe latura lungă (ideal 3000+), JPEG, clară în zona etichetei.
   - Produsul în mijloc, în cele 75% centrale ale înălțimii: imaginea de ofertă taie sus și jos.
   - Aparatul la nivelul etichetei, drept. Pentru borcane, sticle și pahare: din față, nu de sus.

2. Folderul: `templates/mockups/<id>/`, cu `id` din litere mici, cifre și cratimă (ex. `borcan-miere-720`).
   Fotografia se numește `photo.jpg`.

3. Cele 4 puncte (`quad`)
   - Deschide fotografia într-un editor care arată coordonatele cursorului în pixeli (GIMP, Photoshop, Photopea).
   - Notează colțurile zonei unde stă eticheta, în ordinea: stânga sus, dreapta sus, dreapta jos, stânga jos.
   - Coordonatele sunt în pixelii fotografiei originale, `[x, y]`, cu originea în colțul din stânga sus.
   - Pe o suprafață curbă, punctele sunt colțurile etichetei așa cum se văd (marginile din stânga și din dreapta).

4. `template.json` (toate câmpurile necunoscute sunt respinse):

```json
{
  "id": "borcan-miere-720",
  "title": "Borcan de miere 720 ml",
  "placeholder": false,
  "default": false,
  "photo": "photo.jpg",
  "keywords": ["borcan", "miere", "dulceață"],
  "quad": [[1210, 980], [1990, 980], [1990, 1620], [1210, 1620]],
  "label_shape": "rounded",
  "padding": 0.03,
  "cylinder": {"wrap_degrees": 100, "arc_px": 28, "edge_shade": 0.25},
  "blend": {"shade": null, "photo_luminance": false, "strength": 0.8, "opacity": 1.0, "mask": null}
}
```

| Câmp | Ce înseamnă |
| --- | --- |
| `id` | Numele folderului. |
| `title` | Numele produsului, în română. |
| `placeholder` | `false` pentru fotografii reale. |
| `default` | `true` la un singur șablon: cel folosit când contextul clientului nu se potrivește cu nimic. |
| `keywords` | Cuvinte din mesajul clientului care aleg șablonul. Diacriticele și majusculele nu contează; un cuvânt de 4+ litere prinde și formele lui ("borcan" prinde "borcane"). Câștigă cuvântul care apare primul în mesaj. |
| `quad` | Cele 4 puncte de la pasul 3. |
| `label_shape` | Forma dată unui design fără transparență: `rectangle`, `rounded`, `circle`, `oval`. Un design transparent își păstrează forma. |
| `padding` | Margine liberă în zonă, ca fracție (0.03 = 3%). |
| `cylinder` | Doar pentru borcane, sticle, pahare; altfel `null`. `wrap_degrees`: cât din circumferință acoperă zona (o zonă cât 3/4 din lățimea vizibilă a produsului = aproximativ 100). `arc_px`: cu câți pixeli coboară mijlocul marginii de sus față de colțuri (0 dacă fotografia este exact din față; negativ dacă mijlocul urcă). `edge_shade`: întunecare spre margini, 0 - 0.8. |
| `blend.shade` | Opțional, `shade.png`: imagine gri de mărimea fotografiei; 128 = neutru, mai închis = umbră, mai deschis = luciu. |
| `blend.photo_luminance` | `true` ia umbrele direct din fotografie. Merge pe suprafețe de o singură culoare (carton, kraft). Nu se combină cu `shade`. |
| `blend.strength` | Cât de tare se aplică umbrele, 0 - 1. |
| `blend.opacity` | Opacitatea etichetei, de obicei 1. |
| `blend.mask` | Opțional, `mask.png` de mărimea fotografiei: alb unde eticheta se vede, negru unde o acoperă ceva (un deget, o panglică). |

5. Verificare, din folderul `ec-quote`:

```bash
python3 -m pytest tests/mockup -q
python3 -c "from ec_quote.mockup import make_mockup; print(make_mockup('logo.png', 'borcan de miere', 'data/mockups'))"
```

Deschide imaginea rezultată. Dacă eticheta este strâmbă, corectează `quad`; dacă marginile ei nu urmează
curbura, ajustează `arc_px` și `wrap_degrees`.

6. Când un produs are fotografie reală, șterge folderul provizoriu cu aceleași cuvinte cheie
   (două teste verifică lista celor 5 provizorii și se actualizează odată cu ea).
