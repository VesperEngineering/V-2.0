pub mod cards;
pub mod status;
pub mod timeline;
pub mod weights;

use unicode_width::UnicodeWidthChar;

pub(crate) fn sanitize_line(value: &str) -> String {
    value
        .chars()
        .map(|character| {
            if character.is_control()
                || is_unicode_format(character)
                || character.width().unwrap_or(0) == 0
            {
                '?'
            } else {
                character
            }
        })
        .collect()
}

fn is_unicode_format(character: char) -> bool {
    matches!(
        character as u32,
        0x00AD
            | 0x0600..=0x0605
            | 0x061C
            | 0x06DD
            | 0x070F
            | 0x0890..=0x0891
            | 0x08E2
            | 0x180E
            | 0x200B..=0x200F
            | 0x202A..=0x202E
            | 0x2060..=0x2064
            | 0x2066..=0x206F
            | 0xFEFF
            | 0xFFF9..=0xFFFB
            | 0x110BD
            | 0x110CD
            | 0x13430..=0x1343F
            | 0x1BCA0..=0x1BCA3
            | 0x1D173..=0x1D17A
            | 0xE0001
            | 0xE0020..=0xE007F
    )
}
