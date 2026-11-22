//! Cancellation of a running comparison.
//!
//! [`compare`](crate::compare()) cannot be interrupted. To stop a long
//! comparison, run it with [`compare_cancellable`](crate::compare_cancellable)
//! and a [`CancelToken`] (a flag any thread can set, plus an optional
//! deadline), or with [`compare_with_check`](crate::compare_with_check) and
//! a caller-supplied check. The signal is consulted before the work
//! starts, between the phases of the comparison and inside every phase
//! whose cost grows with the input: every 32 768 elements in the linear
//! passes (half-widths, corner enumeration, deviations, classification)
//! and, inside the corner clean-up (the only phase whose cost can grow
//! faster than linearly), after every few tens of thousands of counted
//! elementary steps. Measured in a release build, checks were at most
//! about 11 ms apart (typically well under 1 ms), also for 10 million
//! samples and for the quadratic clean-up case, and a 50 ms deadline
//! returned after at most 54 ms.
//!
//! Two short stretches are not covered. Input validation (one pass over
//! the time arrays, about 16 ms for 10 million samples) runs before the
//! first check, because an invalid input reports its status even when the
//! signal has already fired. Freeing the working buffers after the last
//! check takes a few milliseconds for 10 million samples.
//!
//! A cancelled comparison returns `Err(`[`Cancelled`]`)`, never a
//! [`Status`](crate::Status): cancellation says nothing about the data.
//!
//! On `wasm32-unknown-unknown` `std::time::Instant::now()` panics, so do
//! not give a token a deadline there; the flag works on every target.

use std::fmt;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

/// Why a comparison was stopped.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Cancelled {
    /// The token was cancelled ([`CancelToken::cancel`]) or the
    /// caller-supplied check asked to stop.
    Requested,
    /// The token's deadline passed.
    DeadlineExceeded,
}

impl fmt::Display for Cancelled {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Cancelled::Requested => f.write_str("comparison cancelled"),
            Cancelled::DeadlineExceeded => f.write_str("comparison cancelled: deadline exceeded"),
        }
    }
}

impl std::error::Error for Cancelled {}

/// A cancellation signal: a shared flag plus an optional deadline.
///
/// Clones share the flag, so a clone handed to another thread can cancel
/// the comparison. The deadline belongs to each value:
/// [`with_deadline`](Self::with_deadline) / [`with_timeout`](Self::with_timeout)
/// return a token that shares the flag and stops at the earlier of its
/// existing and the new deadline. A cancelled flag stays cancelled.
///
/// ```
/// use simtest_funnel_core::{compare_cancellable, CancelToken, Cancelled, Options};
/// use std::time::Duration;
///
/// let t = [0.0, 1.0, 2.0];
/// let y = [0.0, 1.0, 0.0];
/// let token = CancelToken::new().with_timeout(Duration::from_secs(10));
/// let r = compare_cancellable(&t, &y, &t, &y, &Options::default(), &token);
/// assert!(r.is_ok());
///
/// token.cancel();
/// let r = compare_cancellable(&t, &y, &t, &y, &Options::default(), &token);
/// assert_eq!(r.err(), Some(Cancelled::Requested));
/// ```
#[derive(Debug, Clone, Default)]
pub struct CancelToken {
    flag: Arc<AtomicBool>,
    deadline: Option<Instant>,
}

impl CancelToken {
    /// A token that is not cancelled and has no deadline.
    pub fn new() -> Self {
        Self::default()
    }

    /// The same flag, with a deadline: the earlier of `deadline` and the
    /// token's current deadline.
    #[must_use]
    pub fn with_deadline(mut self, deadline: Instant) -> Self {
        self.deadline = Some(match self.deadline {
            Some(d) => d.min(deadline),
            None => deadline,
        });
        self
    }

    /// The same flag, with a deadline `timeout` from now (see
    /// [`with_deadline`](Self::with_deadline)). A timeout too large to
    /// represent leaves the deadline unchanged.
    #[must_use]
    pub fn with_timeout(self, timeout: Duration) -> Self {
        match Instant::now().checked_add(timeout) {
            Some(d) => self.with_deadline(d),
            None => self,
        }
    }

    /// Set the shared flag: every comparison using this token or a clone
    /// of it stops at its next checkpoint.
    pub fn cancel(&self) {
        self.flag.store(true, Ordering::Relaxed);
    }

    /// Whether [`cancel`](Self::cancel) was called on this token or a clone.
    pub fn is_cancelled(&self) -> bool {
        self.flag.load(Ordering::Relaxed)
    }

    /// The deadline, if any.
    pub fn deadline(&self) -> Option<Instant> {
        self.deadline
    }

    /// `Err` if the flag is set ([`Cancelled::Requested`]) or the
    /// deadline has passed ([`Cancelled::DeadlineExceeded`]).
    pub fn check(&self) -> Result<(), Cancelled> {
        if self.is_cancelled() {
            return Err(Cancelled::Requested);
        }
        match self.deadline {
            Some(d) if Instant::now() >= d => Err(Cancelled::DeadlineExceeded),
            _ => Ok(()),
        }
    }
}

/// Elementary steps of the corner clean-up between two checks. At a few
/// nanoseconds per step this is typically about 0.1 ms between checks,
/// while the cost of a check (an atomic load, maybe a clock read) is spread
/// over enough work to be unmeasurable.
pub(crate) const CHECK_INTERVAL: usize = 1 << 15;

/// Counts work and calls a check every [`CHECK_INTERVAL`] steps.
pub(crate) struct Checkpoint<'a, C: FnMut() -> Result<(), Cancelled>> {
    check: &'a mut C,
    work: usize,
}

impl<'a, C: FnMut() -> Result<(), Cancelled>> Checkpoint<'a, C> {
    pub(crate) fn new(check: &'a mut C) -> Self {
        Self { check, work: 0 }
    }

    /// Call the check now (phase boundaries).
    #[inline]
    pub(crate) fn now(&mut self) -> Result<(), Cancelled> {
        self.work = 0;
        (self.check)()
    }

    /// Record `steps` units of work; call the check once enough work has
    /// accumulated.
    #[inline]
    pub(crate) fn tick(&mut self, steps: usize) -> Result<(), Cancelled> {
        self.work = self.work.saturating_add(steps);
        if self.work >= CHECK_INTERVAL {
            self.now()
        } else {
            Ok(())
        }
    }

    /// Call `f` on consecutive sub-ranges of `0..n` of at most
    /// [`CHECK_INTERVAL`] elements, in order, and record each range as
    /// work. Used by the linear phases: the loop bodies stay unchanged
    /// (same order of operations, so results are bit-identical), and the
    /// check runs about every [`CHECK_INTERVAL`] elements.
    #[inline]
    pub(crate) fn chunks<F: FnMut(std::ops::Range<usize>)>(
        &mut self,
        n: usize,
        mut f: F,
    ) -> Result<(), Cancelled> {
        let mut start = 0;
        while start < n {
            let end = start + (n - start).min(CHECK_INTERVAL);
            f(start..end);
            self.tick(end - start)?;
            start = end;
        }
        Ok(())
    }
}

/// Run `body` with a [`Checkpoint`] whose check never fires (the
/// non-cancellable entry points and tests).
#[inline]
pub(crate) fn never_cancelled<R>(
    body: impl FnOnce(&mut Checkpoint<'_, fn() -> Result<(), Cancelled>>) -> Result<R, Cancelled>,
) -> R {
    let mut never: fn() -> Result<(), Cancelled> = || Ok(());
    match body(&mut Checkpoint::new(&mut never)) {
        Ok(r) => r,
        Err(_) => unreachable!("a check that never fires cannot cancel"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn new_token_is_not_cancelled() {
        let t = CancelToken::new();
        assert!(!t.is_cancelled());
        assert_eq!(t.deadline(), None);
        assert_eq!(t.check(), Ok(()));
    }

    #[test]
    fn clones_share_the_flag() {
        let t = CancelToken::new();
        let c = t.clone().with_timeout(Duration::from_secs(60));
        c.cancel();
        assert!(t.is_cancelled());
        assert_eq!(t.check(), Err(Cancelled::Requested));
    }

    #[test]
    fn past_deadline_is_exceeded() {
        let t = CancelToken::new().with_deadline(Instant::now() - Duration::from_millis(1));
        assert_eq!(t.check(), Err(Cancelled::DeadlineExceeded));
    }

    #[test]
    fn earlier_deadline_wins() {
        let now = Instant::now();
        let early = now + Duration::from_secs(1);
        let late = now + Duration::from_secs(5);
        let t = CancelToken::new().with_deadline(early).with_deadline(late);
        assert_eq!(t.deadline(), Some(early));
        let t = CancelToken::new().with_deadline(late).with_deadline(early);
        assert_eq!(t.deadline(), Some(early));
    }

    #[test]
    fn huge_timeout_means_no_deadline() {
        let t = CancelToken::new().with_timeout(Duration::MAX);
        assert_eq!(t.deadline(), None);
    }

    #[test]
    fn flag_takes_precedence_over_deadline() {
        let t = CancelToken::new().with_deadline(Instant::now() - Duration::from_millis(1));
        t.cancel();
        assert_eq!(t.check(), Err(Cancelled::Requested));
    }

    #[test]
    fn checkpoint_calls_check_after_interval() {
        let mut calls = 0usize;
        let mut check = || {
            calls += 1;
            Ok(())
        };
        {
            let mut cp = Checkpoint::new(&mut check);
            for _ in 0..CHECK_INTERVAL - 1 {
                cp.tick(1).unwrap();
            }
            cp.tick(1).unwrap();
            cp.tick(CHECK_INTERVAL * 3).unwrap();
            cp.now().unwrap();
        }
        assert_eq!(calls, 3);
    }

    #[test]
    fn display_names_the_reason() {
        assert!(Cancelled::DeadlineExceeded.to_string().contains("deadline"));
        assert!(!Cancelled::Requested.to_string().contains("deadline"));
    }
}
