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
async function loadEvents(fromDate, toDate) {
    try {
        let url = '/api/events';
        if (fromDate && toDate) {
            url += `?from=${encodeURIComponent(fromDate)}&to=${encodeURIComponent(toDate)}`;
        }
        const response = await fetch(url);
        const events = await response.json();
        return Array.isArray(events) ? events : [];
    } catch (error) {
        console.error('Error loading events:', error);
        return [];
    }
}
