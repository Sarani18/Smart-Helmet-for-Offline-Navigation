# 🏍️ Elite Tactical: Pune Mission Route Guide

Use this sequence to test your ESP32 LED patterns. These are the exact steps for the "Blue Line" journey from Shaniwar Wada to Pune Station.

| Step | Action | LED Mode Expected | Instruction Text |
| :--- | :--- | :--- | :--- |
| **1** | **Start** | `CLEAR` | "Head north on Shivaji Road" |
| **2** | **Turn** | `RIGHT_NOW` | "Turn right onto Hidayatulla Road" |
| **3** | **Straight** | `CLEAR` | "Continue for 800m" |
| **4** | **Turn** | `LEFT_NOW` | "Turn left toward MG Road" |
| **5** | **Straight** | `CLEAR` | "Stay on the main road" |
| **6** | **Turn** | `RIGHT_NOW` | "Turn right onto Pune Station Rd" |
| **7** | **Arrive** | `ARRIVED` | "Arrived! Pune Station is on your left" |

---

### 🛠️ Hardware Simulation Commands
You can manually test these in your terminal using `curl` while the server is running:

- **Test Right Turn:**  
  `curl -G "http://10.100.30.164/command" --data-urlencode "cmd=RIGHT_NOW"`
- **Test Left Turn:**  
  `curl -G "http://10.100.30.164/command" --data-urlencode "cmd=LEFT_NOW"`
- **Test Arrival:**  
  `curl -G "http://10.100.30.164/command" --data-urlencode "cmd=ARRIVED"`
