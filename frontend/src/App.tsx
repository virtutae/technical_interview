import { useEffect, useState } from "react";

interface Product {
  supplier_ref: string;
  product_description: string;
  brand: string;
  manufacturer_code: string;
  pack_size: string;
  unit_price_gbp: number;
  vat_rate: string;
  category: string;
  notes: string;
}

interface Match {
  match_type: "identical" | "similar";
  confidence: string | number;
  score: number | null;
  product_a: Product;
  product_b: Product;
  price_difference_gbp: number;
  price_difference_pct: number;
}

interface ApiResponse {
  summary: {
    total_products_a: number;
    total_products_b: number;
    identical_matches: number;
    similar_matches: number;
    unmatched_a: number;
    unmatched_b: number;
  };
  matches: Match[];
  unmatched_a: Product[];
  unmatched_b: Product[];
}

interface Row {
  product: Product;
  supplier: "NovaDent" | "PrimeCare";
  counterpart: Product | null;
  match_type: "identical" | "similar" | null;
  score: number | null;
  price_diff: number | null;
}

function buildRows(data: ApiResponse): Row[] {
  const rows: Row[] = [];

  for (const m of data.matches) {
    rows.push({
      product: m.product_a,
      supplier: "NovaDent",
      counterpart: m.product_b,
      match_type: m.match_type,
      score: m.score,
      price_diff: m.price_difference_gbp,
    });
    rows.push({
      product: m.product_b,
      supplier: "PrimeCare",
      counterpart: m.product_a,
      match_type: m.match_type,
      score: m.score,
      price_diff: -m.price_difference_gbp,
    });
  }

  for (const p of data.unmatched_a) {
    rows.push({
      product: p,
      supplier: "NovaDent",
      counterpart: null,
      match_type: null,
      score: null,
      price_diff: null,
    });
  }

  for (const p of data.unmatched_b) {
    rows.push({
      product: p,
      supplier: "PrimeCare",
      counterpart: null,
      match_type: null,
      score: null,
      price_diff: null,
    });
  }

  return rows;
}

type SortField = "product" | "supplier" | "category" | "price";

export default function App() {
  const [data, setData] = useState<ApiResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sortField, setSortField] = useState<SortField>("product");
  const [sortAsc, setSortAsc] = useState(true);

  useEffect(() => {
    fetch("/comparisons")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <div className="error">Error: {error}</div>;
  if (!data) return <div className="loading">Loading...</div>;

  const allRows = buildRows(data);
  const q = search.trim().toLowerCase();

  const tokens = q ? q.split(/\s+/).filter(Boolean) : [];

  const rowMatchesSearch = (row: Row): boolean => {
    if (tokens.length === 0) return true;
    const haystack = [
      row.product.supplier_ref,
      row.product.product_description,
      row.product.manufacturer_code,
    ]
      .join(" ")
      .toLowerCase();
    return tokens.every((t) => haystack.includes(t));
  };

  const directMatches = new Set<number>();
  allRows.forEach((row, i) => {
    if (rowMatchesSearch(row)) directMatches.add(i);
  });

  const counterpartIncludes = new Set<number>();
  allRows.forEach((row, i) => {
    if (directMatches.has(i) && row.counterpart) {
      const counterpartRef = row.counterpart.supplier_ref;
      allRows.forEach((other, j) => {
        if (other.product.supplier_ref === counterpartRef) {
          counterpartIncludes.add(j);
        }
      });
    }
  });

  const filtered = allRows.filter(
    (_, i) => directMatches.has(i) || counterpartIncludes.has(i)
  );

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    if (sortField === "product") {
      cmp = a.product.product_description.localeCompare(
        b.product.product_description
      );
    } else if (sortField === "supplier") {
      cmp = a.supplier.localeCompare(b.supplier);
    } else if (sortField === "category") {
      cmp = a.product.category.localeCompare(b.product.category);
    } else if (sortField === "price") {
      cmp = a.product.unit_price_gbp - b.product.unit_price_gbp;
    }
    return sortAsc ? cmp : -cmp;
  });

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
  };

  const sortIcon = (field: SortField) =>
    sortField === field ? (sortAsc ? " \u25B2" : " \u25BC") : "";

  const exclusive = allRows.filter((r) => !r.counterpart).length;
  const matched = allRows.filter((r) => r.counterpart).length;

  return (
    <div className="container">
      <h1>Dentstock Price Comparison</h1>

      <div className="summary">
        <div className="stat">
          <span className="stat-value">{allRows.length}</span>
          <span className="stat-label">Total Products</span>
        </div>
        <div className="stat">
          <span className="stat-value">{matched}</span>
          <span className="stat-label">Matched</span>
        </div>
        <div className="stat">
          <span className="stat-value">{exclusive}</span>
          <span className="stat-label">Single Supplier</span>
        </div>
        <div className="stat">
          <span className="stat-value">{data.summary.identical_matches}</span>
          <span className="stat-label">Identical Pairs</span>
        </div>
        <div className="stat">
          <span className="stat-value">{data.summary.similar_matches}</span>
          <span className="stat-label">Similar Pairs</span>
        </div>
      </div>

      <input
        className="search"
        type="text"
        placeholder="Search by Supplier ref, Product Description or Manufacturer code"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      <p className="result-count">
        Showing {sorted.length} of {allRows.length} products
      </p>

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th className="sortable" onClick={() => handleSort("supplier")}>
                Supplier{sortIcon("supplier")}
              </th>
              <th>Supplier Ref</th>
              <th className="sortable" onClick={() => handleSort("product")}>
                Product Description{sortIcon("product")}
              </th>
              <th>Brand</th>
              <th>Manufacturer Code</th>
              <th>Pack Size</th>
              <th className="sortable" onClick={() => handleSort("price")}>
                Unit Price (GBP){sortIcon("price")}
              </th>
              <th>VAT Rate</th>
              <th className="sortable" onClick={() => handleSort("category")}>
                Category{sortIcon("category")}
              </th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={10} className="empty">
                  No products match your search
                </td>
              </tr>
            ) : (
              sorted.map((row, i) => (
                <tr
                  key={i}
                  className={row.counterpart ? "matched" : "exclusive"}
                >
                  <td>
                    <span className={`supplier-badge ${row.supplier.toLowerCase()}`}>
                      {row.supplier}
                    </span>
                  </td>
                  <td>{row.product.supplier_ref}</td>
                  <td>{row.product.product_description}</td>
                  <td>{row.product.brand}</td>
                  <td className="code">{row.product.manufacturer_code}</td>
                  <td>{row.product.pack_size}</td>
                  <td className="price">
                    &pound;{row.product.unit_price_gbp.toFixed(2)}
                  </td>
                  <td>{row.product.vat_rate}</td>
                  <td>{row.product.category}</td>
                  <td>{row.product.notes}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
