"""Generate the SYNTHETIC demo/test fixtures. Every file is invented test material.

Nothing here describes a real company, market, or event. Output goes to
tests/fixtures/synthetic/, physically separate from the authority corpus in data/.
"""
import csv, pathlib

OUT = pathlib.Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "synthetic"
BANNER = "[Sample document - invented for demonstration]\n"

DOCS = {
"arden_price_letter.txt": """From: Arden Chemical Co.
To: Halcyon Beverage Co., Attn: Procurement
Date: February 12, 2024
Re: Price adjustment - food-grade citric acid anhydrous

Dear Customer,
Effective April 1, 2024, Arden Chemical Co. will increase prices on food-grade citric acid anhydrous by 8% for all customers in the United States.
This adjustment is due to sustained increases in energy and freight costs.
Orders shipped before the effective date will be invoiced at current prices.
""",
"bexley_price_letter.txt": """From: Bexley Ingredients LLC
To: Halcyon Beverage Co.
Date: February 20, 2024
Re: Annual price adjustment - citric acid, food grade

Effective April 1, 2024, prices for food-grade citric acid will increase by 8%.
This adjustment is made pursuant to Section 4.2 of the Supply Agreement, which adjusts prices each April 1 by reference to the Corn Dextrose Index.
The adjustment applies to U.S. deliveries of food-grade product only.
""",
"corvane_price_letter.txt": """From: Corvane Acidulants Inc.
To: Halcyon Beverage Co.
Date: March 4, 2024
Re: Citric acid pricing

Effective April 1, 2024, Corvane Acidulants Inc. will increase list prices for food-grade citric acid by 7.5% in the United States.
Customers under fixed-price agreements through 2024 are exempt from this increase.
Corvane has not discussed this adjustment with any competitor.
The increase reflects higher fermentation feedstock costs.
""",
"bexley_supply_agreement.txt": """SUPPLY AGREEMENT between Bexley Ingredients LLC and Halcyon Beverage Co.
Section 2.1 Term. This Agreement runs from April 1, 2022 and renews each April 1 unless terminated on 90 days notice.
Section 4.2 Price Adjustment. On each April 1, the price shall be adjusted by the percentage change in the Corn Dextrose Index over the preceding twelve months, not to exceed 8%.
Section 6.1 Minimum Volume. Buyer shall purchase not less than 400,000 kg per contract year.
""",
"okafor_interview_memo.txt": """INTERVIEW MEMORANDUM - ATTORNEY WORK PRODUCT
Interview date: May 14, 2024
Speaker: Maria Okafor, Director of Procurement, Halcyon Beverage Co. (employed 2019 to present)

1. Okafor stated that Halcyon's beverage specification prohibits the impurity level found in industrial-grade citric acid.
2. Okafor stated that she personally began qualification trials of imported food-grade product from Delmar Import Trading in February 2024, and that qualifying an imported source takes nine months of certification testing.
3. Okafor stated that a Bexley sales representative told her by phone in March 2024: "Everyone is going up eight. You won't find it cheaper elsewhere."
4. Okafor stated that she heard from a former colleague that suppliers discussed pricing at the NAAC annual meeting in January 2024. She did not attend and does not know who was present.
5. Okafor stated that malic acid changes the flavor profile and was rejected for Halcyon's carbonated line.
""",
"trade_article_acidulant_weekly.txt": """Acidulant Weekly - January 29, 2024
NAAC annual meeting draws producers to Phoenix
The North American Acidulants Council held its annual meeting on January 23-24, 2024 in Phoenix.
Executives from Arden Chemical Co. and Bexley Ingredients LLC appeared as panelists on the outlook session.
Corvane Acidulants Inc. is a member of the Council.
In an unrelated lawsuit concerning lysine, plaintiffs alleged that producers agreed to fix prices.
""",
"trade_article_food_ingredient_wire.txt": """Food Ingredient Wire (syndicated) - January 30, 2024
Producers gather in Phoenix for NAAC meeting
The North American Acidulants Council held its annual meeting on January 23-24, 2024 in Phoenix.
Executives from Arden Chemical Co. and Bexley Ingredients LLC appeared as panelists on the outlook session.
Corvane Acidulants Inc. is a member of the Council.
In an unrelated lawsuit concerning lysine, plaintiffs alleged that producers agreed to fix prices.
""",
"arden_q4_earnings_call.txt": """Arden Chemical Co. - Q4 2023 Earnings Call - February 6, 2024
[00:14:32] Chief Financial Officer: We have been planning a price action in acidulants since fall 2023 given where energy costs have gone.
[00:15:10] Chief Financial Officer: We do not comment on competitors' pricing.
""",
}

HEAD = ["Vendor Name", "Inv No", "Line", "Inv Date", "Item", "Item Desc", "Family", "Grade", "Origin",
        "Qty", "UOM", "Ext Amount", "Rebate Alloc", "Freight", "Ship To", "Curr"]
MONTHS = [(2023, m) for m in (10, 11, 12)] + [(2024, m) for m in range(1, 10)]


def rows():
    n = 0
    def row(vendor, y, m, item, desc, fam, grade, origin, qty, uom, unit, rebate, freight, ship):
        nonlocal n
        n += 1
        return [vendor, f"INV-{n:04d}", 1, f"{y}-{m:02d}-15", item, desc, fam, grade, origin, qty, uom,
                f"{qty * unit:.2f}", rebate, f"{freight:.2f}", ship, "USD"]
    for y, m in MONTHS:
        post = (y, m) >= (2024, 4)
        # Arden: invoiced in lb; rebate allocation missing (blank) on three lines.
        yield row("ARDEN CHEMICAL", y, m, "CA-FG-50", "Citric acid anhydrous FG", "citric_acid", "food", "domestic",
                  40000, "LB", 0.864 if post else 0.80, "" if m in (5, 6, 7) else "400.00", 900, "NJ")
        # Bexley: invoiced in kg; client supplied no invoices after March 2024.
        if not post:
            yield row("Bexley Ingredients LLC", y, m, "BX-CIT-F", "Citric acid food grade", "citric_acid", "food",
                      "domestic", 18000, "KG", 1.76, "0.00", 700, "NJ")
        # Corvane: NJ plant follows the increase; TX plant is under a fixed-price agreement.
        yield row("Corvane", y, m, "CV-100F", "Citric acid FG granular", "citric_acid", "food", "domestic",
                  30000, "LB", 0.8815 if post else 0.82, "0.00", 800, "NJ")
        yield row("Corvane", y, m, "CV-100F", "Citric acid FG granular", "citric_acid", "food", "domestic",
                  20000, "LB", 0.82, "0.00", 950, "TX")
        # Delmar: imported product; trial lots before the increase, regular volume after; flat price.
        if (y, m) in ((2024, 2), (2024, 3)) or (y, m) >= (2024, 6):
            yield row("Delmar Import Trading", y, m, "DM-CA-IMP", "Citric acid FG imported", "citric_acid", "food",
                      "import", 15000 if post else 5000, "LB", 0.74, "0.00", 1400, "NJ")
        if m in (2, 8):
            yield row("ARDEN CHEMICAL", y, m, "CA-IND-50", "Citric acid industrial", "citric_acid", "industrial",
                      "domestic", 5000, "LB", 0.61, "0.00", 300, "NJ")
        if m % 2 == 0:
            yield row("Estwick Organics", y, m, "MAL-25", "Malic acid FG", "malic_acid", "food", "domestic",
                      4000, "LB", 1.10, "0.00", 250, "NJ")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in DOCS.items():
        (OUT / name).write_text(BANNER + text)
    with open(OUT / "halcyon_ap_export.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEAD)
        w.writerows(rows())
    print(f"wrote {len(DOCS) + 1} synthetic fixtures to {OUT}")


if __name__ == "__main__":
    main()
