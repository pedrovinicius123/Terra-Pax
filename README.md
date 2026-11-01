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
python setup.py build_ext --inplace
python run_game.py
```

O comando compila os módulos executáveis do jogo e os kernels de logística
com Cython; usa otimização nativa (`-O3` no GCC/Clang, `/O2` no MSVC).
`run_game.py` verifica que o módulo principal compilado está sendo usado.
No Windows, ative o ambiente com `.venv\Scripts\activate` antes de executar
os comandos.

As camadas leves de compatibilidade da logística continuam em Python e
delegam o planejamento de transferências aos kernels Cython. Para executar
diretamente a versão Python durante desenvolvimento, use `python main.py`.

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
adequação de cada mundo. As superfícies combinam continentes e costas
gerados com ruído procedural tridimensional amostrado sobre uma esfera. Isso
mantém os continentes contínuos nas bordas do mapa e nos polos, com proporção
de terra, costas e relevo determinísticos por planeta. As cidades são
aglomerados e estradas gerados sobre essa mesma máscara de terra, não sobre
mapas de luzes terrestres. Na vista 3D, as camadas são interpoladas ao girar;
as luzes aparecem no lado noturno e as nuvens no diurno. Os atlas de nuvens e
estrelas continuam sendo carregados localmente, sem downloads durante a
partida.

A galáxia começa com dez facções controladas por IA ou pelo jogador, com
representantes dos quatro tipos de suitability (**Human**, **Alien**,
**Hybrid** e **Robot**).

Antes de cada partida, escolha qualquer uma das facções para comandar. As
demais recebem controladores de IA.

Os sistemas estelares são distribuídos por uma galáxia de 4000 unidades, com
espaçamento mínimo proporcional à escala da galáxia e inverso à raiz da
quantidade de estrelas. O alcance colonial inicial é de 600 unidades e aumenta
em 100 a cada nível de FTL acima do primeiro. As estrelas, planetas e órbitas
foram reduzidos para manter os astros pequenos em relação às distâncias entre
sistemas.

Colônias recebem luzes urbanas procedurais em cidades geradas sobre continentes
habitáveis. O brilho cresce conforme população e desenvolvimento, tanto no
mapa quanto no visualizador 3D.

## Interface e controles

- Clique em uma estrela ou planeta para selecionar e ver o sistema e os
  detalhes do mundo.
- Selecione um planeta e pressione `V` (ou use **Vista 3D**) para abrir a esfera
  3D gerada localmente; arraste para girar, use a roda para zoom e `Esc`/`V`
  para fechar.
- Linhas tracejadas coloridas conectam sistemas vizinhos colonizados pela mesma
  facção.
- Use a roda do mouse para ampliar/reduzir o mapa (zoom inicial 0,45 e máximo
  120x) e arraste para navegar. `R` recentraliza a galáxia e restaura o zoom.
- As abas **Frota** e **Colônias** organizam naves por função e mundos entre
  capital e colônias; role a roda sobre a lista para navegar e selecione uma
  linha para focar a nave ou o mundo no mapa.
- Em **Visual**, ajuste o detalhe das texturas de 1 a 8; os níveis maiores
  aumentam a resolução das texturas e a malha do visualizador 3D.
- Em **Construção**, escolha entre seis designs de combate (corveta, fragata,
  destroier, cruzador, encouraçado e cruzador de batalha), além de naves
  civis/de exploração, transporte e colonização. Os sprites são coloridos pela
  facção e a lista pode ser rolada.
- Em **Diplom.**, melhore relações por 25 de Energia (+10, até 100), proponha
  pactos de não agressão (relação 45) e acordos comerciais (relação 55), ou
  declare guerra. Alianças exigem acordo comercial e relação 70; acordos
  comerciais aumentam a pesquisa em 5% por parceiro, até 50%. A IA também
  negocia e pode encerrar guerras quando as relações permitem.
- `Espaço` pausa ou retoma a simulação; `F11` alterna tela cheia.
- Os botões no topo controlam pausa e velocidade. Os filtros do mapa alternam
  entre todos os planetas, os da sua facção e os ainda livres.
- As abas laterais reúnem recursos, sistemas, pesquisa, frota, construção e
  diplomacia.

## Logística

A pasta `logistics/` contém a política de logística automática e o visualizador
3D integrado à interface principal. Cada facção encomenda transportadores
civis conforme cresce o número de colônias (até quatro naves). Os transportes
procuram colônias com excedente e espaço de armazenamento, carregam minerais e
fazem as entregas por rotas do mapa; cargas não entregues são mantidas a bordo
até que uma colônia tenha capacidade.

O visualizador 3D é renderizado em software pelo Pygame, usa as mesmas
categorias e sementes procedurais dos planetas 2D e não baixa imagens nem
depende de OpenGL. Os adaptadores de colônia (`logistics_node.pyx`) e o
planejador de transferências (`logistics_manager.pyx`) são extensões Cython
usadas pelo gerenciador logístico quando compiladas. O jogo mantém versões
Python equivalentes como fallback. Para ativar as extensões no ambiente virtual
da raiz (com um compilador C/C++ instalado), execute:

```bash
venv/bin/python -m pip install -r requirements.txt
venv/bin/python setup.py build_ext --inplace
```

No visualizador, clique e arraste sobre o planeta para girá-lo; use a roda
para aproximar ou afastar. As luzes de cidades aparecem na face noturna e
acompanham a rotação da superfície. Os mapas e sprites são carregados dos
assets locais; o jogo continua funcionando offline.

### Créditos dos assets visuais

Os assets abaixo são carregados localmente pelo jogo:

- Nuvens: [NASA Blue Marble — cloud combined](https://assets.science.nasa.gov/content/dam/science/esd/eo/content-feature/bluemarble/images/cloud_combined_2048.jpg).
- Fundo estelar: [NASA/JPL-Caltech/UCLA — WISE all-sky image (PIA15481)](https://images-assets.nasa.gov/image/PIA15481/PIA15481~orig.jpg).
- Sprites de naves: [Kenney — Space Shooter Extension](https://kenney.nl/assets/space-shooter-extension), licença [CC0](https://creativecommons.org/publicdomain/zero/1.0/); a licença original acompanha os arquivos em `graphics/assets/ships/LICENSE.txt`.

Os antigos atlas terrestres de superfície e luzes ainda podem existir em
`graphics/assets/`, mas não são usados na geração dos planetas: superfície
[NASA Earth Observatory](https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57730/land_ocean_ice_2048.jpg)
e luzes
[NASA Blue Marble](https://assets.science.nasa.gov/content/dam/science/esd/eo/content-feature/bluemarble/images/land_ocean_ice_lights_2048.jpg).
Continentes, relevo e cidades são criados localmente a partir da semente do
mundo. Os arquivos NASA de nuvens e céu são apenas camadas visuais e não
definem sua geografia. Créditos e condições de uso devem ser verificados para
cada imagem e contexto de redistribuição; esta lista não declara os arquivos
NASA como CC0 nem como livres de direitos de terceiros. O uso das imagens
não implica endosso da NASA ao jogo. Consulte também a
[política de imagens e mídia da NASA](https://www.nasa.gov/nasa-brand-center/images-and-media/).

## Tecnologias

- Python
- Pygame CE
- NetworkX
- NumPy
