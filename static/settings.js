/* settings.js – pool-pH version
   - keeps only pH-probe + relay logic
   - guards every DOM lookup so missing elements don’t crash the script
   - calls /api/… endpoints
*/

/* ───────── helpers ───────── */
async function getJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`${url} → HTTP ${resp.status}`);
    return resp.json();
}
async function postJSON(url, body) {
    const resp = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
    });
    if (!resp.ok) throw new Error(`${url} → HTTP ${resp.status}`);
    return resp.json();
}

/* ───────── USB-roles UI ───────── */
const deviceSelect   = document.getElementById("usb_device_select");
const assignBtn      = document.getElementById("assign_ph_btn");
const clearBtn       = document.getElementById("clear_ph_btn");
const statusSpan     = document.getElementById("ph_usb_status");

function populateDeviceDropdown(devices, assigned) {
    if (!deviceSelect) return;
    deviceSelect.innerHTML = "";
    devices.forEach(d => {
        const opt = document.createElement("option");
        opt.value = d.device;
        opt.textContent = d.device;
        if (d.device === assigned) opt.selected = true;
        deviceSelect.appendChild(opt);
    });
    if (!assigned) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "-- select --";
        opt.selected = true;
        deviceSelect.insertBefore(opt, deviceSelect.firstChild);
    }
}

async function rescanUsb() {
    console.log("Rescanning USB devices…");
    try {
        const [devs, settings] = await Promise.all([
            getJSON("/api/settings/usb_devices"),
            getJSON("/api/settings")
        ]);

        const assigned = settings.usb_roles?.ph_probe || null;
        populateDeviceDropdown(devs, assigned);

        if (statusSpan) {
            statusSpan.textContent = assigned ? assigned : "not assigned";
            statusSpan.className   = assigned ? "ok" : "warn";
        }
    } catch (err) {
        console.error("USB scan failed:", err);
    }
}

if (assignBtn && deviceSelect) {
    assignBtn.addEventListener("click", async () => {
        const devicePath = deviceSelect.value || null;
        try {
            await postJSON("/api/settings/assign_usb", { role: "ph_probe", device: devicePath });
            await rescanUsb();
        } catch (e) { alert(e.message); }
    });
}
if (clearBtn) {
    clearBtn.addEventListener("click", async () => {
        try {
            await postJSON("/api/settings/assign_usb", { role: "ph_probe", device: null });
            await rescanUsb();
        } catch (e) { alert(e.message); }
    });
}

/* ───────── init ───────── */
document.addEventListener("DOMContentLoaded", () => {
    rescanUsb();
    // re-scan every 15 s so unplug events show up
    setInterval(rescanUsb, 15000);
});
