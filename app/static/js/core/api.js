// קריאות GET לשרת שמחזירות JSON (לוח חודשי, חגים, אירועים)

async function fetchMonthData(year, month) {
    const response = await fetch(`/api/calendar/${year}/${month}`);
    if (!response.ok) {
        throw new Error(`Failed to load calendar ${year}-${month}`);
    }
    return response.json();
}

async function fetchJewishMonth(year, month) {
    const response = await fetch(`/api/jewish-events/month/${year}/${month}`);
    if (!response.ok) {
        throw new Error(`Failed to load jewish events ${year}-${month}`);
    }
    return response.json();
}

// פונקציות טיפול באירועים
async function loadEvents() {
    try {
        const response = await fetch('/api/events');
        const events = await response.json();
        return events;
    } catch (error) {
        console.error('Error loading events:', error);
        return [];
    }
}
