# Terra Pax

Terra Pax é um jogo de estratégia espacial em tempo real feito em Python e
Pygame. Explore sistemas estelares, colonize planetas, pesquise tecnologias e
conduza sua facção em uma galáxia que continua evoluindo enquanto você joga.

## Executar

Com Python 3.12 ou superior, em uma versão compatível com o NetworkX 3.7
(a versão 3.14.1 é explicitamente incompatível):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

No Windows, ative o ambiente com `.venv\Scripts\activate`.

## Tempo e calendário

A partida começa no ano **2150**. Cada segundo de tempo simulado avança o
calendário em um ano: o primeiro segundo completo termina em 2151. O ano
aparece em destaque na barra superior. Pausar interrompe o avanço; as opções
de velocidade fazem o calendário correr mais rápido (por exemplo, em 2x,
dois anos simulados passam por segundo real).

Os tempos de construção e as taxas de pesquisa também usam o tempo simulado,
portanto seus valores na interface são apresentados em anos e por ano.

## Planetas gerados proceduralmente

Cada nova partida gera aleatoriamente sistemas, planetas, perfis de
suitability e a aparência 2D dos mundos. Cada planeta tem uma pontuação de
0 a 1 para as quatro categorias:

- **Human** — mundos de tons oceânicos e verdes.
- **Alien** — mundos de tons violetas e magenta.
- **Hybrid** — mundos de tons verdes e turquesa.
- **Robot** — mundos de tons minerais e metálicos.

Um perfil escolhe uma categoria dominante e atribui pontuações às demais.
Essa afinidade também orienta a escolha de planetas natais das facções. A
textura ilustrada é criada localmente a partir do perfil e da identidade do
planeta; ela aparece no mapa quando ampliado e no painel de detalhes ao
selecionar um planeta. As pontuações continuam visíveis para comparar a
adequação de cada mundo.

Os sistemas estelares são distribuídos por uma galáxia de 4000 unidades, com
espaçamento mínimo proporcional à escala da galáxia e inverso à raiz da
quantidade de estrelas. O alcance colonial inicial é de 600 unidades e aumenta
em 100 a cada nível de FTL acima do primeiro.

## Interface e controles

- Clique em uma estrela ou planeta para selecionar e ver o sistema e os
  detalhes do mundo.
- Use a roda do mouse para ampliar/reduzir o mapa (zoom inicial 0,45 e máximo
  120x) e arraste para navegar. `R` recentraliza a galáxia e restaura o zoom.
- As abas **Frota** e **Colônias** organizam naves por função e mundos entre
  capital e colônias; role a roda sobre a lista para navegar e selecione uma
  linha para focar a nave ou o mundo no mapa.
- `Espaço` pausa ou retoma a simulação; `F11` alterna tela cheia.
- Os botões no topo controlam pausa e velocidade. Os filtros do mapa alternam
  entre todos os planetas, os da sua facção e os ainda livres.
- As abas laterais reúnem recursos, sistemas, pesquisa, frota, construção e
  diplomacia.

## Tecnologias

- Python
- Pygame CE
- NetworkX
- NumPy
