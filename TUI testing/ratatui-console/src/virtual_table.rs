use std::cmp::Ordering;
use std::ops::Range;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct VirtualTable<T> {
    rows: Vec<T>,
    order: Vec<usize>,
    offset: usize,
}

impl<T> VirtualTable<T> {
    pub fn new(rows: Vec<T>) -> Self {
        let order = (0..rows.len()).collect();
        Self {
            rows,
            order,
            offset: 0,
        }
    }

    pub fn rows(&self) -> &[T] {
        &self.rows
    }

    pub fn set_offset(&mut self, offset: usize) {
        self.offset = offset.min(self.order.len().saturating_sub(1));
    }

    pub fn visible_range(&self, height: usize) -> Range<usize> {
        if height == 0 || self.order.is_empty() {
            return 0..0;
        }
        let window_length = height.saturating_add(2).min(self.order.len());
        let start = self.offset.saturating_sub(1);
        let end = start.saturating_add(window_length).min(self.order.len());
        end.saturating_sub(window_length)..end
    }

    pub fn visible_rows(&self, height: usize) -> impl Iterator<Item = &T> {
        self.order[self.visible_range(height)]
            .iter()
            .map(|position| &self.rows[*position])
    }

    pub fn sort_by(&mut self, mut compare: impl FnMut(&T, &T) -> Ordering) {
        let rows = &self.rows;
        self.order
            .sort_by(|left, right| compare(&rows[*left], &rows[*right]));
    }

    pub fn filter_by(&mut self, mut include: impl FnMut(&T) -> bool) {
        self.order = self
            .rows
            .iter()
            .enumerate()
            .filter_map(|(position, row)| include(row).then_some(position))
            .collect();
        self.offset = self.offset.min(self.order.len().saturating_sub(1));
    }
}
