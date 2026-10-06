"""Build the PDF report: overlay rendered formulas on the 3 raw-LaTeX code blocks the Docs PDF export leaves
in the Framework tab, then merge Portfolio run + Framework.
Usage: python build_pdf.py <portfolio-tab.pdf> <framework-tab.pdf> <out.pdf>  (tab PDFs from the Docs export)."""
import io, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from pypdf import PdfReader, PdfWriter

plt.rcParams["mathtext.fontset"] = "cm"
W, H = 612.0, 792.0
BG = (248/255, 248/255, 246/255)
# page index (0-based) -> (text yMin, yMax in top-down pt, list of lines; each line = list of formulas)
BLOCKS = {
    1: (543.08, 571.95, [[r"$\sigma_p=\sigma\sqrt{\dfrac{1+(N-1)\rho}{N}}$",
                          r"$N_{\mathrm{eff}}=\dfrac{N}{1+(N-1)\rho}$",
                          r"$\dfrac{S_p}{S}=\sqrt{N_{\mathrm{eff}}}$"]]),
    2: (594.83, 623.70, [[r"$RC_i=\dfrac{w_i\,(\Sigma w)_i}{\sigma_p}$",
                          r"$DR=\dfrac{\Sigma_i\, w_i\sigma_i}{\sigma_p}$",
                          r"$N_{\mathrm{eff}}=DR^2$"]]),
    3: (630.08, 674.70, [[r"$L=\dfrac{\sigma^*}{\sigma_p}$",
                          r"$r(L)=r_f+L(\mu_p-r_f)-\max(L-1,\,0)\,s$"],
                         [r"$g(L)=r(L)-\dfrac{1}{2}L^2\sigma_p^2$",
                          r"$L_{\mathrm{Kelly}}=\dfrac{\mu_p-r_f-s}{\sigma_p^2}$"]]),
}

def overlay(ymin, ymax, lines):
    fig = plt.figure(figsize=(W/72, H/72))
    fig.patch.set_alpha(0)
    top, bot = ymin - 10.5, ymax + 10.5            # match the grey box padding
    fig.add_artist(Rectangle((52/W, 1 - bot/H), (560-52)/W, (bot-top)/H,
                             transform=fig.transFigure, facecolor=BG, edgecolor="none"))
    n = len(lines)
    for k, line in enumerate(lines):
        yc = top + (bot - top) * (k + 0.5) / n
        xs = [68 + j * (470 / len(line)) for j in range(len(line))]
        for x, f in zip(xs, line):
            fig.text(x/W, 1 - yc/H, f, fontsize=12.5 if n == 1 else 11, va="center", ha="left", color="#1f1f1f")
    buf = io.BytesIO(); fig.savefig(buf, format="pdf", transparent=True); plt.close(fig)
    buf.seek(0); return PdfReader(buf).pages[0]

port, frame, out = sys.argv[1:4]
w = PdfWriter()
for p in PdfReader(port).pages: w.add_page(p)
for i, p in enumerate(PdfReader(frame).pages):
    if i in BLOCKS: p.merge_page(overlay(*BLOCKS[i]))
    w.add_page(p)
w.add_metadata({"/Title": "Dalio Holy Grail — Portfolio run Oct 2026 + Framework", "/Author": "Casey"})
with open(out, "wb") as fh: w.write(fh)
print("wrote", out, len(w.pages), "pages")
