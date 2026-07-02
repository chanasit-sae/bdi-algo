---
title: "ชุดข้อมูลคลื่นของเครื่องช่วยหายใจจากผู้ป่วย ICU"
track: "Health"
domain:
  - "Clinical"
  - "ICU"
  - "Time Series"
source:
  - "โรงพยาบาลศรีนครินทร์ มหาวิทยาลัยขอนแก่น"
total_records: null
sampled_records: 17000
filetype:
  - "csv"
  - "json"

---

# ชุดข้อมูลคลื่นของเครื่องช่วยหายใจจากผู้ป่วย ICU

## คำอธิบาย
ชุดข้อมูลคลื่นสัญญาณจากเครื่องช่วยหายใจ (ventilator) ของผู้ป่วยใน ICU โดยบันทึกข้อมูลทุกวันเป็นระยะเวลา **2–3 สัปดาห์** (24 ช่วง/วัน, 1 ช่วง/ชั่วโมง) ที่ rate **25 Hz**

ข้อมูลประกอบด้วยคลื่นสัญญาณ 3 แกนหลัก: Flow, Pressure, Volume พร้อมข้อมูล demographics, diagnosis, และ operation ของผู้ป่วย

[สไลด์นำเสนอชุดข้อมูลตัวอย่าง](./Ventilator_Waveform_Case.pdf)

## ฟิลด์ข้อมูล

### ไฟล์ JSON (ข้อมูลผู้ป่วย)
| ฟิลด์ | คำอธิบาย |
|-------|----------|
| `bed` | รหัสผู้ป่วย (encrypted) และจำนวนวันที่อยู่ใน ICU |
| `captures` | array: การบันทึกค่า signal จาก ventilator ในหนึ่งวัน |
| `demographic` | ข้อมูล demographics: น้ำหนัก (BW), ส่วนสูง (HT), BMI |
| `diagnosis` | การวินิจฉัยของแพทย์: PDx (หลัก), SDx (ร่วม) |
| `operation` | หัตถการที่ทำระหว่าง admit |
| `patient` | ข้อมูลบุคคล: อายุ, เพศ (ช/ญ) |
| `ven` | หมายเลขเครื่อง ventilator |
| `time` | เวลาที่เริ่มบันทึก |
| `raw_data` | ไฟล์ข้อมูลที่บันทึกได้จาก ventilator |

### ไฟล์ CSV (สัญญาณเครื่องช่วยหายใจ)
| ฟิลด์ | คำอธิบาย | หน่วย |
|-------|--------|------|
| `Flow (l/min)` | อัตราการไหลของอากาศที่เครื่องส่งให้ผู้ป่วย | L/min |
| `Pressure (cmH2O)` | ความดันในทางเดินหายใจ | cmH₂O |
| `Volume (ml)` | ปริมาตรอากาศที่ส่งเข้าสู่/ออกจากผู้ป่วย | mL |

## โครงสร้างไฟล์
| ไฟล์ | รูปแบบ |
|------|--------|
| [`data_dictionary_smarticu.xlsx`](data_dictionary_smarticu.xlsx) | Excel (Data Dictionary) |
| [`smart_icu_data/`](smart_icu_data/) | Directory: ข้อมูล ventilator ตามผู้ป่วย |

## โจทย์ / แนวทางวิเคราะห์
- **Abnormality Detection**: ตรวจจับความผิดปกติของคลื่นสัญญาณ ventilator
- **Pattern Analysis**: วิเคราะห์รูปแบบคลื่นหายใจ (breathing patterns)
- **Clinical Decision Support**: ช่วยแพทย์ตัดสินใจตั้งค่า ventilator
- **Patient Status Prediction**: พยากรณ์สถานะผู้ป่วยจากสัญญาณ
- **ICU Length of Stay Prediction**: พยากรณ์ระยะเวลาอยู่ใน ICU
- **Breathing Mode Classification**: จำแนกโหมดการช่วยหายใจ

## หมายเหตุ
- ข้อมูลเป็น time series แบบ high-frequency (25 Hz)
- จำนวนตัวอย่าง: **17,000 รายการ**
