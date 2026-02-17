#!/usr/bin/env python3
"""Generate formatted PDF files from YAML recipe files."""

import subprocess
import sys
from pathlib import Path

import yaml
from fpdf import FPDF


# Colors
BROWN_DARK = (62, 39, 35)
BROWN_MED = (93, 64, 55)
TEXT_COLOR = (33, 33, 33)
GRAY_ACCENT = (188, 170, 164)
GRAY_TEXT = (97, 97, 97)
LINK_COLOR = (0, 0, 180)

EXCLUDE_DIRS = {"PDF", "tools", ".git", ".claude"}


def format_time(time_str):
    """Convert '00:30:00' to '30 min'."""
    try:
        parts = str(time_str).split(":")
        hours = int(parts[0])
        mins = int(parts[1])
        if hours > 0:
            return f"{hours}h {mins}min"
        return f"{mins} min"
    except (ValueError, IndexError):
        return str(time_str)


def format_ingredient(ing):
    """Format a single ingredient dict into a display string."""
    parts = []
    amount_str = str(ing.get("amount", "")).strip()
    unit_str = str(ing.get("unit", "")).strip()

    if amount_str:
        parts.append(amount_str)
    if unit_str:
        parts.append(unit_str)
    parts.append(ing["item"])

    line = " ".join(parts)

    if "amount_alt" in ing and "unit_alt" in ing:
        line += f"  ({ing['amount_alt']} {ing['unit_alt']})"
    elif "amount_alt" in ing:
        line += f"  ({ing['amount_alt']})"

    if ing.get("optional"):
        line += "  [optional]"
    if ing.get("brand"):
        line += f"  [Brand: {ing['brand']}]"
    if ing.get("ref"):
        ref_name = Path(ing["ref"]).stem.replace("_", " ").title()
        line += f"  (see: {ref_name})"
    if ing.get("garnish"):
        line += "  [garnish]"

    return line


def format_substitution(sub):
    """Format a substitution item."""
    line = format_ingredient(sub)
    target = sub.get("replaces") or sub.get("for", "")
    if target:
        line += f"  \u2192 replaces {target}"
    return line


class RecipePDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        self._setup_fonts()

    def _setup_fonts(self):
        """Try to register DejaVu Sans; fall back to built-in Helvetica."""
        # Static paths to check first
        font_dirs = [
            Path(__file__).resolve().parent / "fonts",
            Path("/usr/share/fonts/truetype/dejavu"),
            Path("/usr/share/fonts/TTF"),
            Path("/usr/share/fonts/dejavu-sans-fonts"),
        ]

        # Try fc-match to find fonts (works on NixOS and other systems)
        for font_name in ["DejaVuSans.ttf", "DejaVuSans-Bold.ttf"]:
            try:
                result = subprocess.run(
                    ["fc-match", "-f", "%{file}", font_name],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    font_dir = Path(result.stdout.strip()).parent
                    if font_dir not in font_dirs:
                        font_dirs.insert(0, font_dir)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        for font_dir in font_dirs:
            regular = font_dir / "DejaVuSans.ttf"
            bold = font_dir / "DejaVuSans-Bold.ttf"
            if regular.exists() and bold.exists():
                self.add_font("DejaVu", "", str(regular))
                self.add_font("DejaVu", "B", str(bold))
                self._font_name = "DejaVu"
                return
        self._font_name = "Helvetica"

    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font(self._font_name, "", 8)
        self.set_text_color(*GRAY_TEXT)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def _section_header(self, title):
        """Render a styled section header with rule line."""
        if self.get_y() > 250:
            self.add_page()
        self.ln(4)
        self.set_font(self._font_name, "B", 13)
        self.set_text_color(*BROWN_MED)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*GRAY_ACCENT)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(3)

    def _bullet_line(self, text, indent=0):
        """Render a bulleted line."""
        self.set_font(self._font_name, "", 10)
        self.set_text_color(*TEXT_COLOR)
        self.set_x(22 + indent)
        self.multi_cell(166 - indent, 5, f"\u2022  {text}", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def _numbered_line(self, number, text, indent=0):
        """Render a numbered step."""
        self.set_font(self._font_name, "", 10)
        self.set_text_color(*TEXT_COLOR)
        prefix = f"{number}.  "
        self.set_x(22 + indent)
        self.multi_cell(166 - indent, 5, f"{prefix}{text}", new_x="LMARGIN", new_y="NEXT")
        self.ln(1.5)

    def render_header(self, data):
        """Render recipe title and metadata."""
        # Title
        self.set_font(self._font_name, "B", 24)
        self.set_text_color(*BROWN_DARK)
        self.multi_cell(0, 12, data["name"], new_x="LMARGIN", new_y="NEXT")

        # Rule
        self.set_draw_color(*GRAY_ACCENT)
        self.set_line_width(0.5)
        self.line(20, self.get_y(), 190, self.get_y())
        self.set_line_width(0.2)
        self.ln(4)

        # Metadata line
        meta_parts = []
        if "region" in data:
            meta_parts.append(f"Region: {data['region']}")
        if "ethnicity" in data:
            meta_parts.append(f"Ethnicity: {data['ethnicity']}")
        if "restaurant" in data:
            meta_parts.append(f"Restaurant: {data['restaurant']}")
        if "category" in data:
            meta_parts.append(f"Category: {data['category']}")
        if meta_parts:
            self.set_font(self._font_name, "", 10)
            self.set_text_color(*GRAY_TEXT)
            self.cell(0, 6, " | ".join(meta_parts), new_x="LMARGIN", new_y="NEXT")
            self.ln(2)

        # Time / yield
        time_parts = []
        if "prep_time" in data:
            time_parts.append(f"Prep: {format_time(data['prep_time'])}")
        if "cook_time" in data:
            time_parts.append(f"Cook: {format_time(data['cook_time'])}")
        if "yield" in data:
            y = str(data["yield"])
            if "yield_unit" in data:
                y += f" {data['yield_unit']}"
            time_parts.append(f"Yield: {y}")
        if "method" in data:
            time_parts.append(f"Method: {data['method']}")
        if time_parts:
            self.set_font(self._font_name, "", 10)
            self.set_text_color(*GRAY_TEXT)
            self.cell(0, 6, " | ".join(time_parts), new_x="LMARGIN", new_y="NEXT")
            self.ln(2)

        # Source URLs
        if "source" in data:
            self.set_font(self._font_name, "", 8)
            self.set_text_color(*LINK_COLOR)
            for key in ["url", "url2"]:
                if key in data["source"]:
                    url = data["source"][key]
                    self.cell(0, 5, url, link=url, new_x="LMARGIN", new_y="NEXT")
                    self.ln(1)

        self.ln(4)

    def render_ingredients(self, ingredients, indent=0):
        """Render a list of ingredients."""
        for ing in ingredients:
            self._bullet_line(format_ingredient(ing), indent=indent)

    def render_steps(self, steps, indent=0):
        """Render numbered steps."""
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                # e.g. {optional: "do something"} from YAML key-value syntax
                for key, val in step.items():
                    step = f"{key}: {val}"
            self._numbered_line(i, step, indent=indent)

    def render_component(self, comp):
        """Render a single component (sub-recipe)."""
        self.set_font(self._font_name, "B", 12)
        self.set_text_color(*BROWN_MED)
        label = comp["name"]
        if "yield" in comp:
            y = str(comp["yield"])
            if "yield_unit" in comp:
                y += f" {comp['yield_unit']}"
            label += f"  (yields {y})"
        self.set_x(22)
        self.cell(0, 7, f"\u25B8 {label}", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

        if "ingredients" in comp:
            self.set_font(self._font_name, "", 9)
            self.set_text_color(*GRAY_TEXT)
            self.set_x(26)
            self.cell(0, 5, "Ingredients:", new_x="LMARGIN", new_y="NEXT")
            self.ln(1)
            self.render_ingredients(comp["ingredients"], indent=10)

        if "steps" in comp:
            self.set_font(self._font_name, "", 9)
            self.set_text_color(*GRAY_TEXT)
            self.set_x(26)
            self.cell(0, 5, "Steps:", new_x="LMARGIN", new_y="NEXT")
            self.ln(1)
            self.render_steps(comp["steps"], indent=10)

        if "substitutions" in comp:
            self.set_font(self._font_name, "", 9)
            self.set_text_color(*GRAY_TEXT)
            self.set_x(26)
            self.cell(0, 5, "Substitutions:", new_x="LMARGIN", new_y="NEXT")
            self.ln(1)
            for sub in comp["substitutions"]:
                self._bullet_line(format_substitution(sub), indent=10)

        if "optional" in comp and isinstance(comp["optional"], list):
            self.set_font(self._font_name, "", 9)
            self.set_text_color(*GRAY_TEXT)
            self.set_x(26)
            self.cell(0, 5, "Optional:", new_x="LMARGIN", new_y="NEXT")
            self.ln(1)
            self.render_ingredients(comp["optional"], indent=10)

        self.ln(2)

    def render_optional_section(self, data):
        """Render the optional section, handling both list and dict forms."""
        opt = data.get("optional")
        if not opt:
            return

        self._section_header("Optional")

        if isinstance(opt, list):
            self.render_ingredients(opt)
        elif isinstance(opt, dict):
            if "components" in opt:
                for comp in opt["components"]:
                    self.render_component(comp)
            if "ingredients" in opt:
                self.render_ingredients(opt["ingredients"])

    def render_recipe(self, data):
        """Render a complete recipe."""
        self.alias_nb_pages()
        self.add_page()
        self.render_header(data)

        if "components" in data:
            self._section_header("Components")
            for comp in data["components"]:
                self.render_component(comp)

        if "ingredients" in data:
            self._section_header("Ingredients")
            self.render_ingredients(data["ingredients"])

        self.render_optional_section(data)

        if "steps" in data:
            self._section_header("Steps")
            self.render_steps(data["steps"])

        if "steps_alt" in data:
            self._section_header("Alternative Steps")
            self.render_steps(data["steps_alt"])

        if "substitutions" in data:
            self._section_header("Substitutions")
            for sub in data["substitutions"]:
                self._bullet_line(format_substitution(sub))

        if "garnishes" in data:
            self._section_header("Garnishes")
            for g in data["garnishes"]:
                self._bullet_line(g["item"])

        if "notes" in data:
            self._section_header("Notes")
            for note in data["notes"]:
                self._bullet_line(note)


def find_recipe_files(repo_root):
    """Find all YAML recipe files, excluding non-recipe directories."""
    files = sorted(repo_root.rglob("*.yaml"))
    return [
        f
        for f in files
        if not any(part in EXCLUDE_DIRS for part in f.relative_to(repo_root).parts)
    ]


def main():
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    build_dir = repo_root / "PDF"

    recipe_files = find_recipe_files(repo_root)

    if not recipe_files:
        print("No recipe files found.")
        return 1

    print(f"Found {len(recipe_files)} recipe files.\n")

    success_count = 0
    error_count = 0

    for yaml_path in recipe_files:
        rel_path = yaml_path.relative_to(repo_root)
        output_path = build_dir / rel_path.with_suffix(".pdf")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(yaml_path, "r") as f:
                data = yaml.safe_load(f)

            if not data or "name" not in data:
                print(f"  SKIP: {rel_path} -- no 'name' field")
                error_count += 1
                continue

            pdf = RecipePDF()
            pdf.render_recipe(data)
            pdf.output(str(output_path))
            success_count += 1
            print(f"  OK: {rel_path}")

        except Exception as e:
            error_count += 1
            print(f"  ERROR: {rel_path} -- {e}")

    print(f"\nDone. {success_count} PDFs generated, {error_count} errors.")
    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
