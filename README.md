# Was drogen

Home Assistant-integratie die bepaalt of je de was buiten kunt hangen: live uit je eigen weerstation, en per uur vooruit uit één of twee weersverwachtingen.

Alles zit in één integratie met een wizard. Geen losse template-sensoren, automatiseringen of tekst-helpers.

## Wat je krijgt

Eén apparaat met vijf entiteiten (ID's voor een Nederlandstalige HA):

| Entiteit | Wat |
| --- | --- |
| `sensor.was_drogen_droogscore` | Score 0–8 van nu, met advies, reden en punten per factor als attributen |
| `binary_sensor.was_drogen_buiten_hangen` | Aan vanaf de hang-grens (standaard 6) |
| `sensor.was_drogen_droogverwachting` | Beste venster vandaag of morgen; alle uren en dagen als attributen |
| `sensor.was_drogen_volgend_droogvenster` | Tijdstip waarop het volgende goede venster begint |
| `sensor.was_drogen_eerste_regen` | Eerste uur met neerslag in de verwachting |

## Installeren via HACS

1. HACS → ⋮ → **Aangepaste repositories** → voeg de URL van deze repository toe, type **Integratie**.
2. Zoek **Was drogen**, installeer en herstart Home Assistant.
3. Instellingen → Apparaten & diensten → **Integratie toevoegen** → **Was drogen**.

## De wizard

**Stap 1 – Weerstation.** Alleen temperatuur en luchtvochtigheid (of dauwpunt) zijn verplicht. Optioneel: VPD, wind, windvlagen, regenintensiteit, regen afgelopen uur en zoninstraling. Ontbrekende waarden worden berekend; eenheden (°F, m/s, mph, kPa, inch) worden automatisch omgerekend.

**Stap 2 – Weersverwachting.** Kies een primaire en optioneel een aanvullende weerentiteit. Per uur wint de primaire bron; velden die daar ontbreken (bijvoorbeeld luchtvochtigheid bij KNMI) en latere uren komen uit de aanvullende bron.

Aanbevolen voor Nederland: **primair KNMI** (heeft zoninstraling, 24 uur vooruit), **aanvullend Met.no** (heeft luchtvochtigheid, ruim 2 dagen vooruit).

Alles is achteraf te wijzigen via **Configureren**: weerstation, weersverwachting, en drempels en tijden.

## Hoe de score werkt

| Factor | 0 punten | 1 punt | 2 punten | 3 punten |
| --- | --- | --- | --- | --- |
| Dampdrukdeficit (VPD) | < 4 hPa | ≥ 4 | ≥ 6 | ≥ 10 |
| Dauwpuntspreiding | < 5 °C | ≥ 5 | ≥ 8 | – |
| Wind | < 3 km/h | ≥ 3, of > 38 | 8 t/m 38 | – |
| Zoninstraling | < 150 W/m² | ≥ 150 | – | – |

**Stopfactoren** zetten de score direct op 0: regen (intensiteit > 0, of meer dan 0,2 mm het afgelopen uur), dauwpuntspreiding onder 3 °C, of windvlagen boven 60 km/h.

Alle grenzen zijn instelbaar. De verwachting gebruikt dezelfde regels. Heeft een bron geen zoninstraling, dan telt "zon" als UV-index ≥ 1 en bewolking < 60 %. Dauwpunt en VPD worden uit temperatuur en luchtvochtigheid berekend met de Magnus-formule.

## Werking

- **Live-score:** wordt opnieuw berekend bij elke nieuwe meting van een stationssensor.
- **Verwachting:** wordt elk uur opgehaald met `weather.get_forecasts` (type `hourly`), voor vandaag en de twee dagen erna, tussen 07:00 en 20:00 (instelbaar).
- Mislukt één bron, dan gaat het door met de andere; de fout staat in het attribuut `fouten` van de droogverwachting.

## Dashboard

In [`dashboard/was-drogen-view.yaml`](dashboard/was-drogen-view.yaml) staat een complete weergave met alleen standaardkaarten: advies met puntentabel, verwachting per uur als gekleurde blokjes met het beste venster per dag, eerste regen en een grafiek van de score.

## Ontwikkelen

```bash
pip install pytest-homeassistant-custom-component
pytest
```

De rekenlogica staat in `scoring.py` zonder Home Assistant-afhankelijkheden, en wordt getest met echte KNMI- en Met.no-data.
