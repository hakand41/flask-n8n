from flask import Flask, render_template, request, redirect, url_for, flash, make_response, session
import requests
from datetime import datetime
import pdfkit
import os
import re

app = Flask(__name__)
app.secret_key = 'test12345_bu_bir_gizli_anahtar_degistirin' 

WEBHOOK_URL = 'http://localhost:5678/webhook/6035ddf2-cc41-40a0-a310-01d7f577e4bc' 
WKHTMLTOPDF_PATH = r'D:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe' 
try:
    config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)
except OSError:
    print(f"UYARI: wkhtmltopdf yolu bulunamadı veya hatalı: {WKHTMLTOPDF_PATH}")
    print("PDF oluşturma özelliği çalışmayabilir.")
    config = None

DOCTORS = {
    "Dr. Hakan Değer": {"email": "degerhakan41@gmail.com", "title": "Kardiyolog"},
    "Dr. Ayşe Yılmaz": {"email": "ayse.yilmaz@example.com", "title": "Dahiliye Uzmanı"},
    "Dr. Mehmet Öz": {"email": "mehmet.oz@example.com", "title": "Genel Cerrah"}
}
PATIENTS = {
    "Hakan Değer": {"email": "degerhakan41@gmail.com", "mrn": "12345", "dob": "1985-04-15", "gender": "E", "name_hl7": "DEĞER^HAKAN^A"},
    "Zeynep Kaya": {"email": "zeynep.kaya@example.com", "mrn": "67890", "dob": "1990-07-22", "gender": "K", "name_hl7": "KAYA^ZEYNEP"},
    "Ali Veli": {"email": "ali.veli@example.com", "mrn": "11223", "dob": "1978-12-01", "gender": "E", "name_hl7": "VELİ^ALİ"}
}
BASVURU_SIKAYETLERI = [
    "Genel Sağlık Kontrolü", "Yorgunluk ve Halsizlik", "Baş Ağrısı", "Karın Ağrısı",
    "Mide Bulantısı ve Kusma", "Öksürük ve Soğuk Algınlığı", "Ateş", "Nefes Darlığı",
    "Eklem Ağrıları", "Cilt Problemleri", "Uyku Bozuklukları", "Stres ve Anksiyete",
    "Diyabet Takibi", "Hipertansiyon Takibi", 
    "Laboratuvar Test İsteği (Doktor Yönlendirmesiyle)", "Diğer"
]
TIBBI_OYKU_SECENEKLERI = [
    "Hipertansiyon", "Diyabet (Şeker Hastalığı)", "Kalp Hastalığı (Koroner Arter, Yetmezlik vb.)",
    "Astım", "KOAH (Kronik Obstrüktif Akciğer Hastalığı)", 
    "Tiroid Hastalığı (Hipotiroidi, Hipertiroidi vb.)", "Böbrek Yetmezliği / Hastalığı",
    "Karaciğer Hastalığı (Siroz, Hepatit vb.)", "Romatizmal Hastalık (Artrit vb.)",
    "Nörolojik Hastalık (Epilepsi, Migren, Parkinson vb.)",
    "Psikiyatrik Rahatsızlık (Depresyon, Anksiyete Bozukluğu vb.)", "Kanser Öyküsü",
    "Geçirilmiş Önemli Ameliyat", "Sürekli Kullanılan İlaçlar", 
    "Bilinen Alerji (İlaç, Besin vb.)", "Sigara Kullanımı (Aktif / Bırakmış)",
    "Alkol Kullanımı (Düzenli / Sosyal)", "Ailede Önemli Kronik Hastalık Öyküsü",
    "Belirtilecek Başka Bir Durum Yok / Bilinmiyor"
]

def clean_report_text(report_text):
    if not report_text: return ""
    match = re.search(r"```text\s*\n?(.*?)\n?```", report_text, re.DOTALL | re.IGNORECASE)
    if match: cleaned_text = match.group(1)
    else:
        unwanted_phrases = [
            r"Tamamdır.*?hazırlayacağım:", r"Kan tahlili sonuçlarını değerlendirmek için.*?rapor hazırlayacağım:",
            r"Tabii.*?hazırlayacağım:", r"Elbette.*?hazırlayacağım:",
        ]
        cleaned_text = report_text
        for phrase in unwanted_phrases:
            cleaned_text = re.sub(phrase, "", cleaned_text, flags=re.DOTALL | re.IGNORECASE)
    cleaned_text = re.sub(r"^\s*---\s*\n", "", cleaned_text, flags=re.MULTILINE)
    cleaned_text = re.sub(r"\n\s*---\s*$", "", cleaned_text, flags=re.MULTILINE)
    cleaned_text = re.sub(r'\n\s*\n+', '\n\n', cleaned_text) 
    return cleaned_text.strip()

def parse_report_structure(text):
    elements = []
    if not text: return elements
    lines = text.split('\n')
    table_data = {"headers": [], "rows": []}
    in_table_section = False 
    for line_raw in lines:
        line = line_raw.strip()
        if not line: 
            if in_table_section and (table_data["headers"] or table_data["rows"]):
                elements.append({"type": "table", "data": dict(table_data)})
                table_data = {"headers": [], "rows": []}
                in_table_section = False
            continue
        if line.startswith('|') and line.endswith('|'):
            parts = [p.strip() for p in line.strip('|').split('|')]
            if all('---' in p for p in parts) or all(p.replace(':','').strip() == '---' for p in parts): 
                if not table_data["headers"] and elements and elements[-1].get("type") == "_temp_header_row_": # .get() kullanımı
                    table_data["headers"] = elements.pop()["content"]
                in_table_section = True
                continue
            if not in_table_section and not table_data["headers"] : 
                elements.append({"type": "_temp_header_row_", "content": parts})
                in_table_section = True
            elif in_table_section: 
                if not table_data["headers"]: 
                    if elements and elements[-1].get("type") == "_temp_header_row_": # .get() kullanımı
                        table_data["headers"] = elements.pop()["content"]
                    else: 
                        table_data["headers"] = parts
                        continue 
                table_data["rows"].append(parts)
            continue
        if in_table_section:
            if table_data["headers"] or table_data["rows"]:
                if elements and elements[-1].get("type") == "_temp_header_row_" and not table_data["headers"]: # .get() kullanımı
                    table_data["headers"] = elements.pop()["content"]
                if table_data["headers"]:
                    elements.append({"type": "table", "data": dict(table_data)})
            table_data = {"headers": [], "rows": []}
            in_table_section = False
        match_h_general = re.match(r"^(\d+(\s*\.\s*\d+)*)\s*\.?\s+(.*)", line)
        match_li = re.match(r"^\*\s+(.*)", line)
        if match_li:
            elements.append({"type": "li", "content": match_li.group(1).strip()})
        elif match_h_general:
            level_str = match_h_general.group(1)
            content = match_h_general.group(3).strip()
            level = level_str.count('.') + 1
            if level == 1: elements.append({"type": "h1", "content": content})
            elif level == 2: elements.append({"type": "h2", "content": content})
            elif level >= 3: elements.append({"type": "h3", "content": content})
            else: elements.append({"type": "p", "content": line})
        else: elements.append({"type": "p", "content": line})
    if in_table_section and (table_data["headers"] or table_data["rows"]):
        if elements and elements[-1].get("type") == "_temp_header_row_" and not table_data["headers"]: # .get() kullanımı
             table_data["headers"] = elements.pop()["content"]
        if table_data["headers"]:
            elements.append({"type": "table", "data": dict(table_data)})
    elements = [el for el in elements if el.get("type") != "_temp_header_row_"] # .get() kullanımı
    final_elements = []
    current_list_items = []
    for el in elements:
        if el.get("type") == "li": # .get() kullanımı
            current_list_items.append(el.get("content", ""))
        else:
            if current_list_items:
                final_elements.append({"type": "ul", "items": list(current_list_items)}) 
                current_list_items = [] 
            final_elements.append(el) 
    if current_list_items:
        final_elements.append({"type": "ul", "items": list(current_list_items)}) 
    return final_elements

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        doktorAd_selected = request.form.get('doktorAd','').strip()
        hastaAd_selected = request.form.get('hastaAd','').strip()
        basvuruSikayetleri_list = request.form.getlist('basvuruSikayeti') 
        tibbiOyku_list = request.form.getlist('tibbiOyku') 
        doktor_data = DOCTORS.get(doktorAd_selected)
        patient_data = PATIENTS.get(hastaAd_selected)
        if not doktor_data: flash('Lütfen geçerli bir doktor seçin.', 'danger'); return redirect(url_for('index'))
        if not patient_data: flash('Lütfen geçerli bir hasta seçin.', 'danger'); return redirect(url_for('index'))
        if not basvuruSikayetleri_list: flash('Lütfen en az bir başvuru şikayeti seçin.', 'danger'); return redirect(url_for('index'))
        doktorMail = doktor_data['email']
        hastaMail = patient_data['email']
        patientMR = patient_data['mrn']
        patient_name_hl7 = patient_data['name_hl7'] 
        patient_dob_yyyymmdd = patient_data.get('dob', '19000101').replace('-', '')
        patient_gender_hl7 = patient_data.get('gender', 'U')
        if patient_gender_hl7 == "E": patient_gender_hl7 = "M"
        elif patient_gender_hl7 == "K": patient_gender_hl7 = "F"
        else: patient_gender_hl7 = "U"
        try:
            test_count = int(request.form.get('test_count','0'))
            if test_count <= 0 : flash('Lütfen en az bir test girin veya geçerli bir sayı seçin.', 'danger'); return redirect(url_for('index'))
        except ValueError: flash('Lütfen geçerli bir test sayısı seçin.','danger'); return redirect(url_for('index'))
        tests = []
        for i in range(1, test_count + 1):
            code = request.form.get(f'test_{i}_code','').strip()
            name = request.form.get(f'test_{i}_name','').strip()
            value_str = request.form.get(f'test_{i}_value','').strip()
            unit = request.form.get(f'test_{i}_unit','').strip()
            ref_range = request.form.get(f'test_{i}_range','').strip()
            if not all([code, name, value_str, unit, ref_range]): flash(f'Test {i} ("{name if name else code}") için tüm alanları doldurun.','danger'); return redirect(url_for('index'))
            try: value = float(value_str) 
            except ValueError: flash(f'Test {i} ("{name if name else code}") değeri sayısal olmalı: "{value_str}"','danger'); return redirect(url_for('index'))
            tests.append({'code': code, 'name': name, 'value': value, 'unit': unit, 'range': ref_range})
        if not tests: flash('Hiç test verisi girilmedi.', 'danger'); return redirect(url_for('index'))
        now = datetime.now()
        msg_date_time = now.strftime('%Y%m%d%H%M%S') 
        report_date_display = now.strftime('%Y-%m-%d %H:%M:%S') 
        hdr = f'MSH|^~\\&|LIS_FLASK_APP|LAB_SISTEMI|EMR_SISTEMI|HASTANE_XYZ|{msg_date_time}||ORU^R01|MSGID{msg_date_time}|P|2.3\r'
        pid = f'PID|1||{patientMR}^^^HASTANE_XYZ^MR||{patient_name_hl7}||{patient_dob_yyyymmdd}|{patient_gender_hl7}|||||||||\r'
        panel_code_name = f"{tests[0]['code']}^{tests[0]['name']}" if tests else "KAN_TAHLILI_PANELI^Genel Kan Tahlili"
        obr = (f'OBR|1|ORD{patientMR}{now.strftime("%S%f")[:8]}|FIL{patientMR}{now.strftime("%S%f")[:8]}|'
               f'{panel_code_name}|||{msg_date_time[:8]}|||||||||Dr. {doktorAd_selected}\r')
        segments = [hdr, pid, obr]
        for idx, t in enumerate(tests, start=1):
            normality_flag = "N" 
            segments.append(f'OBX|{idx}|NM|{t["code"]}^{t["name"]}||{t["value"]}|{t["unit"]}|{t["range"]}|{normality_flag}|||F\r')
        hl7Message = ''.join(segments)
        payload = {
            "doktorAd": doktorAd_selected, "hastaAd": hastaAd_selected, "hastaMail": hastaMail,
            "doktorMail": doktorMail, "basvuruSikayeti": basvuruSikayetleri_list, 
            "tibbiOyku": tibbiOyku_list, "hl7Message": hl7Message
        }
        try:
            resp = requests.post(WEBHOOK_URL, json=payload, timeout=60)
            resp.raise_for_status()
            response_data = resp.json()
            if not response_data or not isinstance(response_data, list) or not response_data[0] or not isinstance(response_data[0], dict) or 'output' not in response_data[0]:
                flash('N8N yanıtında beklenen "output" alanı bulunamadı veya format hatalı.', 'danger')
                print("Hatalı N8N Yanıtı:", response_data); return redirect(url_for('index'))
            raw_output = response_data[0].get('output', '')
            if not raw_output.strip(): flash('N8N\'den boş rapor yanıtı alındı.', 'warning')
            cleaned_output = clean_report_text(raw_output)
            parsed_report_elements = parse_report_structure(cleaned_output)
            session['parsed_report'] = parsed_report_elements
            session['rapor_hasta_details'] = {"name": hastaAd_selected, **patient_data}
            session['rapor_doktor_details'] = {"name": doktorAd_selected, **doktor_data}
            session['rapor_tarih'] = report_date_display
            session['basvuru_sikayetleri_display'] = basvuruSikayetleri_list 
            session['tibbi_oyku_display'] = tibbiOyku_list 
            return redirect(url_for('rapor'))
        except requests.Timeout: flash('N8N servisine bağlanırken zaman aşımı oluştu. Lütfen tekrar deneyin.', 'danger')
        except requests.ConnectionError: flash('N8N servisine bağlanılamadı. Servisin çalıştığından emin olun.', 'danger')
        except requests.HTTPError as e: flash(f'N8N servisinden HTTP hatası alındı: {e.response.status_code} - {e.response.reason}', 'danger'); print(f"N8N HTTP Hatası Detayı: {e.response.text}")
        except requests.RequestException as e: flash(f'N8N ile iletişimde bir sorun oluştu: {e}', 'danger')
        except ValueError as e: flash(f'N8N yanıtı JSON formatında değil veya hatalı: {e}', 'danger'); print(f"N8N JSON Decode Hatası, Yanıt: {resp.text if 'resp' in locals() else 'Yanıt alınamadı'}")
        except Exception as e: flash(f'Rapor işlenirken genel bir hata oluştu: {e}', 'danger'); print(f"Genel Hata: {type(e).__name__} - {e}")
        return redirect(url_for('index'))
    return render_template('index.html', 
                           doctors=DOCTORS, patients=PATIENTS, 
                           basvuru_sikayetleri=BASVURU_SIKAYETLERI,
                           tibbi_oyku_secenekleri=TIBBI_OYKU_SECENEKLERI)

@app.route('/rapor')
def rapor():
    parsed_report = session.get('parsed_report')
    hasta_details = session.get('rapor_hasta_details')
    doktor_details = session.get('rapor_doktor_details')
    report_date = session.get('rapor_tarih')
    basvuru_sikayetleri_list = session.get('basvuru_sikayetleri_display') 
    tibbi_oyku_list = session.get('tibbi_oyku_display')

    # ---- YENİ HATA AYIKLAMA KODU ----
    print("\n--- Debugging parsed_report in /rapor route ---")
    if isinstance(parsed_report, list):
        print(f"parsed_report is a list with {len(parsed_report)} elements.")
        for i, elem in enumerate(parsed_report):
            print(f"Element {i}: {elem}") # Elementin tamamını yazdır
            if isinstance(elem, dict):
                elem_type = elem.get("type")
                print(f"  Element {i} dictionary type: {elem_type}")
                if elem_type == "ul":
                    if 'items' not in elem:
                        print(f"  CRITICAL WARNING: Element {i} is 'ul' but has NO 'items' key.")
                    elif not isinstance(elem.get('items'), list): # Sadece list mi diye kontrol et
                        print(f"  CRITICAL WARNING: Element {i} is 'ul' and 'items' is NOT A LIST. Type: {type(elem.get('items'))}, Value: {elem.get('items')}")
                    else:
                        print(f"  Element {i} is 'ul' and 'items' IS a list with {len(elem.get('items'))} sub-items.")
            else:
                print(f"  Element {i} is not a dictionary. Type: {type(elem)}")
    elif parsed_report is None:
        print("parsed_report is None.")
    else:
        print(f"parsed_report is not a list. Type: {type(parsed_report)}, Value: {parsed_report}")
    print("--- End Debugging parsed_report ---\n")
    # ---- HATA AYIKLAMA KODU SONU ----

    if hasta_details is None or doktor_details is None or report_date is None:
        flash("Görüntülenecek rapor bilgileri eksik. Lütfen formu yeniden gönderin.", "warning")
        return redirect(url_for('index'))
    return render_template(
        'rapor.html',
        parsed_report=parsed_report if parsed_report is not None else [],
        hasta=hasta_details, doktor=doktor_details, tarih=report_date,
        basvuru_sikayetleri=basvuru_sikayetleri_list if basvuru_sikayetleri_list is not None else [],
        tibbi_oyku=tibbi_oyku_list if tibbi_oyku_list is not None else []
    )

@app.route('/rapor/pdf')
def rapor_pdf():
    parsed_report = session.get('parsed_report')
    hasta_details = session.get('rapor_hasta_details')
    doktor_details = session.get('rapor_doktor_details')
    report_date = session.get('rapor_tarih')
    basvuru_sikayetleri_list = session.get('basvuru_sikayetleri_display')
    tibbi_oyku_list = session.get('tibbi_oyku_display')
    if hasta_details is None or doktor_details is None or report_date is None:
        flash("PDF oluşturmak için rapor bilgileri eksik. Lütfen formu yeniden gönderin.", "warning")
        return redirect(url_for('index'))
    if config is None:
        flash("PDF motoru yapılandırılamadığı için PDF oluşturulamıyor.", "danger")
        return redirect(url_for('rapor'))
    pdf_options = {
        'page-size': 'A4', 'margin-top': '20mm', 'margin-right': '15mm',
        'margin-bottom': '20mm', 'margin-left': '15mm', 'encoding': "UTF-8",
        'no-outline': None, 'enable-local-file-access': None,
        'footer-right': '"Sayfa [page] / [topage]"', 'footer-font-size': '8', 'footer-spacing': '5'
    }
    try:
        html = render_template(
            'rapor_pdf.html', 
            parsed_report=parsed_report if parsed_report is not None else [],
            hasta=hasta_details, doktor=doktor_details, tarih=report_date,
            basvuru_sikayetleri=basvuru_sikayetleri_list if basvuru_sikayetleri_list is not None else [],
            tibbi_oyku=tibbi_oyku_list if tibbi_oyku_list is not None else []
        )
        pdf = pdfkit.from_string(html, False, configuration=config, options=pdf_options)
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=kan_tahlili_raporu.pdf'
        return response
    except FileNotFoundError:
         flash(f"wkhtmltopdf belirtilen yolda bulunamadı: {WKHTMLTOPDF_PATH}", "danger")
    except Exception as e:
        flash(f"PDF oluşturulurken bir hata oluştu: {e}", "danger")
        print(f"PDF Oluşturma Hatası: {type(e).__name__} - {e}")
    return redirect(url_for('rapor'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)