"""Terminal menu code to browse tracks."""

import enum
import webbrowser
from collections.abc import Sequence

import cursesmenu
import web_cache

import amg

# menu items are numbered from 1, those below this threshold need an extra leading space to align
SINGLE_DIGIT_INDEX_MAX = 9
COLUMN_SEP = "\t"


class AmgMenu(cursesmenu.CursesMenu):
    """Custom menu to choose review/track."""

    UserAction = enum.Enum("UserAction", ("DEFAULT", "OPEN_REVIEW", "DOWNLOAD_AUDIO"))

    def __init__(
        self,
        *,
        reviews: Sequence[amg.ReviewMetadata],
        known_reviews: amg.KnownReviews,
        http_cache: web_cache.WebCache,
        mode: amg.PlayerMode,
        selected_idx: int | None,
    ) -> None:
        """Build a menu with one item per review."""
        menu_subtitle = {amg.PlayerMode.MANUAL: "Select a track", amg.PlayerMode.RADIO: "Select track to start from"}
        super().__init__(
            f"AMG Player v{amg.__version__}",
            f"{mode.name.capitalize()} mode: {menu_subtitle[mode]} "
            "(ENTER to play, "
            "D to download audio, "
            "R to open review, "
            "Q to exit)",
            show_exit_item=True,
        )
        self.user_action = self.UserAction.DEFAULT
        if selected_idx is not None:
            self.current_option = selected_idx
        review_strings = self.reviewsToStrings(reviews, known_reviews, http_cache)
        for review, review_string in zip(reviews, review_strings, strict=True):
            self.items.append(ReviewItem(review, review_string, self))

    def process_user_input(self) -> int:
        """
        Override key handling to add "open review" and "quick exit" features.

        See cursesmenu.CursesMenu.process_user_input
        """
        self.user_action = self.UserAction.DEFAULT
        c = super().process_user_input()
        if c in frozenset(map(ord, "rR")):
            self.user_action = self.UserAction.OPEN_REVIEW
            self.select()
        elif c in frozenset(map(ord, "dD")):
            self.user_action = self.UserAction.DOWNLOAD_AUDIO
            self.select()
        elif c in frozenset(map(ord, "qQ")):
            # select last item (exit item)
            self.current_option = self.last_item_index
            self.select()
        return c

    def get_last_user_action(self) -> AmgMenu.UserAction:
        """Return last user action when item was selected."""
        return self.user_action

    @staticmethod
    def reviewsToStrings(
        reviews: Sequence[amg.ReviewMetadata],
        known_reviews: amg.KnownReviews,
        http_cache: web_cache.WebCache,
    ) -> list[str]:
        """Generate a list of string representations of reviews."""
        lines = []
        for review in reviews:
            try:
                play_count = known_reviews.getPlayCount(review.url)
                played = (
                    f"Last played: {known_reviews.getLastPlayed(review.url).strftime('%x %H:%M')} "
                    f"({play_count} time{'s' if play_count > 1 else ''})"
                )
            except KeyError:
                if review.url in http_cache:
                    review_page = amg.fetch_page(review.url, http_cache=http_cache)
                    if amg.get_embedded_track(review_page, http_cache)[0] is None:
                        played = "No track"
                    else:
                        played = "Last played: never"
                else:
                    played = "Last played: never"
            lines.append((f"{review.artist} - {review.album}", played))
        # auto align/justify
        max_lens = [0] * len(lines[0])
        for line in lines:
            for i, s in enumerate(line):
                max_lens[i] = max(max_lens[i], len(s))
        return [
            "".join(
                (
                    " " if i < SINGLE_DIGIT_INDEX_MAX else "",
                    COLUMN_SEP.join(s.ljust(max_len + 1) for s, max_len in zip(line, max_lens, strict=True)),
                )
            )
            for i, line in enumerate(lines)
        ]

    @staticmethod
    def setupAndShow(
        mode: amg.PlayerMode,
        reviews: Sequence[amg.ReviewMetadata],
        known_reviews: amg.KnownReviews,
        http_cache: web_cache.WebCache,
        selected_idx: int | None = None,
    ) -> tuple[int, AmgMenu.UserAction] | None:
        """Set up and display interactive menu, return selected review index or None if exist requested."""
        menu = AmgMenu(
            reviews=reviews, known_reviews=known_reviews, http_cache=http_cache, mode=mode, selected_idx=selected_idx
        )
        menu.show()
        idx = menu.selected_option
        return None if (idx == len(reviews)) else (idx, menu.get_last_user_action())


class ReviewItem(cursesmenu.items.MenuItem):
    """Custom menu item (menu line), overriden to support several actions per item."""

    def __init__(self, review: amg.ReviewMetadata, review_string: str, menu: AmgMenu) -> None:
        """Build a menu item for a review."""
        super().__init__(review_string, menu)
        self.review = review

    def action(self) -> None:
        """React to user action."""
        assert isinstance(self.menu, AmgMenu)
        if self.menu.get_last_user_action() is AmgMenu.UserAction.OPEN_REVIEW:
            webbrowser.open_new_tab(self.review.url)
            self.should_exit = False
        else:
            self.should_exit = True
