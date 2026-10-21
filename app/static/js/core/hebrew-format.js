// טקסט תאריכים לתצוגה: יום עברי, שמות חודשים, כותרת הסרגל, תאריך קצר בכותרת המודל

function get_hebrew_day(day) {
    const days = {
        1: 'א', 2: 'ב', 3: 'ג', 4: 'ד', 5: 'ה', 6: 'ו', 7: 'ז', 8: 'ח', 9: 'ט', 10: 'י',
        11: 'יא', 12: 'יב', 13: 'יג', 14: 'יד', 15: 'טו', 16: 'טז', 17: 'יז', 18: 'יח', 19: 'יט', 20: 'כ',
        21: 'כא', 22: 'כב', 23: 'כג', 24: 'כד', 25: 'כה', 26: 'כו', 27: 'כז', 28: 'כח', 29: 'כט', 30: 'ל'
    };
    return days[day] || '';
}

function getShortMonthName(month) {
    const shortMonths = ['ינו', 'פבר', 'מרץ', 'אפר', 'מאי', 'יוני',
                        'יולי', 'אוג', 'ספט', 'אוק', 'נוב', 'דצמ'];
    return shortMonths[month];
}

const GREGORIAN_MONTH_NAMES_HE = [
    'ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
    'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר',
];

function formatToolbarLabel(gregYear, gregMonth, hebrewMonth, hebrewYear) {
    const gregPart = `${GREGORIAN_MONTH_NAMES_HE[gregMonth - 1]} ${gregYear}`;
    const hebPart = [hebrewMonth, hebrewYear].filter(Boolean).join(' ');
    return hebPart ? `${gregPart} | ${hebPart}` : gregPart;
}

function formatShortGregorian(dateStr) {
    if (!dateStr) {
        return '';
    }

    const parts = dateStr.split('-');
    if (parts.length !== 3) {
        return dateStr;
    }

    return `${Number(parts[2])}/${Number(parts[1])}`;
}

function formatShortHebrew(hebrewDate) {
    if (!hebrewDate) {
        return '';
    }

    // "ח אב 5786" / "ח אב תשפ\"ו" / "ח אב ה'תשפ\"ו" -> "ח אב"
    return hebrewDate
        .replace(/\s+\d{3,4}$/, '')
        .replace(/\s+ה?'?[\u05d0-\u05ea]+"?[\u05d0-\u05ea]*$/, '')
        .trim();
}
