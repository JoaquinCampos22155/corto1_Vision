# corto1_Vision

Notebook de Vision por Computadora con implementacion de **Task 3** usando Transfer Learning con VGG16 en PyTorch.

## Estructura esperada del dataset

El notebook usa `torchvision.datasets.ImageFolder`, por lo que el dataset debe quedar asi:

```text
archive/
  Anthracnose/
  Bacterial Canker/
  Cutting Weevil/
  Die Back/
  Gall Midge/
  Healthy/
  Powdery Mildew/
  Sooty Mould/
```

## Instalacion

```bash
python -m pip install -r requirements.txt
```

## Ejecucion

1. Descarga el dataset de Kaggle de hojas de mango.
2. Extraelo localmente en la carpeta raiz del proyecto con nombre `archive/`.
3. Abre `Corto.ipynb`.
4. Ejecuta todas las celdas en orden (`Run All`).

## Notas de repositorio

- El dataset **no se versiona** en Git para evitar un repo pesado.
- `.gitignore` ya excluye:
  - `archive/`
  - `data/`
  - `*.zip`

