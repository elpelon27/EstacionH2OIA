# Hablemos de evaluaciones genómicas con el Dr Matías Bermann

- **URL**: https://www.youtube.com/watch?v=VVChW3a0h-A
- **Duración**: 1543s
- **Tema**: agropecuario
- **Analizado con**: google/gemini-3.1-pro-preview
- **Fecha**: 2026-10-17T00:23:55.737698+00:00

## TL;DR
- Entrevista con el Dr. Matías Bermann sobre la evolución de las evaluaciones genéticas y genómicas en el mejoramiento animal, destacando el desarrollo del 'single step'.
- Comparación detallada entre enfoques bayesianos (Gibbs sampler) y frecuentistas (REML, BLUP), explicando por qué estos últimos son preferidos en evaluaciones rutinarias por su velocidad y estabilidad.
- Análisis de los desafíos computacionales en poblaciones masivas al invertir matrices complejas (como las matrices H y G).
- Descripción de metodologías avanzadas para optimizar el cómputo, como Monte Carlo REML, el algoritmo APY y single-step SNP-BLUP.
- Presentación de avances recientes en la extensión de modelos de umbral frecuentistas para múltiples características categóricas.

## Momentos clave
- **00:00:23**: Presentación del invitado: Dr. Matías Bermann, implicado en el programa BLUPF90 de la Universidad de Georgia.
- **00:01:44**: Bermann menciona a los colaboradores clave del BLUPF90 (Misztal, Legarra, Aguilar, Tsuruta, Masuda, entre otros).
- **00:02:23**: Historia del mejoramiento genético: paper de Fisher (años 1920), bases de caracteres poligénicos y valor de cría.
- **00:03:26**: Paper de 2001 de Meuwissen: hipótesis de que los marcadores genéticos aumentarían la precisión de las evaluaciones.
- **00:05:38**: Explicación de las evaluaciones genómicas de múltiples pasos y sus desventajas (pseudoregistros, falta de propagación).
- **00:06:41**: Historia del single step: desarrollo independiente y simultáneo por dos grupos (Georgia y Dinamarca).
- **00:09:30**: Ventaja del single step: propagación de información genómica a animales no genotipados, clave en poblaciones masivas.
- **00:11:39**: Comparación bayesiano vs frecuentista: REML es más rápido y requiere menos input; Gibbs sampler exige verificar convergencia.
- **00:12:32**: Profundización en la comparación práctica entre la estimación bayesiana y la frecuentista.
- **00:13:29**: Monte Carlo REML: reemplaza la inversión de la matriz de coeficientes por simulaciones, reduciendo tiempos drásticamente.
- **00:13:57**: Razones por las que se utiliza BLUP frecuentista en evaluaciones genéticas de rutina (velocidad y estabilidad numérica).
- **00:16:51**: Planteamiento del reto computacional que supone la inversión de la matriz conjugada (matriz H).
- **00:18:04**: Desglose de los tres componentes principales que conforman la matriz H inversa.
- **00:19:55**: Explicación de métodos alternativos (APY, GT BLUP, single-step SNP-BLUP) para manejar la inversión de la matriz G.
- **00:21:52**: Bermann comparte su investigación reciente sobre la extensión del modelo de umbral a múltiples características categóricas.

## Hechos clave
- El mejoramiento genético de caracteres poligénicos inició con el paper de Fisher en los años 1920, y en 2001 Meuwissen hipotetizó el impacto de los marcadores genéticos.
- El método 'single step' fue desarrollado independientemente en 2009-2010 por el grupo de Georgia (Misztal, Legarra, Aguilar) y el de Dinamarca (Christensen, Lund).
- En las evaluaciones de múltiples pasos, no había propagación de datos genómicos a animales no genotipados, un problema crítico en poblaciones como el ganado lechero de EE.UU.
- La estimación frecuentista mediante REML es más rápida, requiere menos configuración manual y garantiza mayor estabilidad numérica que los métodos bayesianos (Gibbs sampler).
- Monte Carlo REML permite reducir el tiempo de cómputo de semanas a un par de horas al evitar inversiones matriciales complejas.
- La matriz H inversa es estructuralmente más sencilla de construir que la matriz H original, componiéndose de la inversa del pedigrí, la inversa genómica y la inversa del pedigrí de genotipados.
- Para poblaciones con millones de animales, se utilizan métodos como el algoritmo APY o single-step SNP-BLUP para evitar la inversión directa y costosa de la matriz G.
- Recientemente se desarrolló una metodología que permite usar modelos frecuentistas multicaracteres para variables categóricas (modelo de umbral), superando limitaciones de costo computacional.

## Citas
> La ventaja del single step es propagación, y la facilidad que tiene para ser aplicado a modelos más complejos.
> Fue desarrollada por dos grupos completamente separados... iban a presentar lo mismo y no lo sabían.
> La estimación frecuentista mediante REML es mucho más rápida y requiere menos conocimiento, menos experiencia y menos input del usuario.
> Uno en las evaluaciones genéticas requiere una cierta estabilidad numérica y temporal que te la suelen dar más esos métodos frecuentistas.
> El valor de cría es básicamente el mérito genético de los animales.
> Lo que yo me dedico más es a la metodología y lo último que hicimos fue extender el modelo de umbral, que es para caracteres categóricos, a múltiples características.

## Entidades / Conceptos
Matías Bermann, BLUPF90, Universidad de Georgia, Ignacio Misztal, Andrés Legarra, Ignacio Aguilar, Daniela Lourenco, Ole Christensen, Mogens Lund, Fisher, C.R. Henderson, Meuwissen, Agustín Blasco, Jose Pérez González, Alberto García Cortés, Robin Thompson, Estadística para Adultos (canal), byols, Genetics, Finlandia, Holanda, Venezuela

Evaluación genética vs evaluación genómica, Valor de cría (mérito genético), BLUP y REML, Modelos mixtos (C.R. Henderson), Matriz de parentesco / matriz de relaciones, Matriz H, Matriz G y Matriz A, Evaluación genómica de múltiples pasos (pseudoregistros), Single step / Single-step SNP-BLUP, Enfoque bayesiano (Gibbs sampler) vs frecuentista, Monte Carlo REML, Algoritmo APY, GT BLUP, Iteración en datos (optimización de memoria), Modelo de umbral (caracteres categóricos), Metafundadores y modelos no lineales

## Transcript
[00:00:02] Saludos, bienvenidos al canal de Estadística para Adultos, donde vemos
[00:00:04] Estadística para Adultos, donde vemos diferentes metodologías estadísticas
[00:00:07] diferentes metodologías estadísticas utilizadas en investigación agropecuaria
[00:00:10] utilizadas en investigación agropecuaria con especial énfasis en el mejoramiento
[00:00:12] con especial énfasis en el mejoramiento genético animal. En esta oportunidad
[00:00:15] genético animal. En esta oportunidad vamos a compartir experiencias,
[00:00:17] vamos a compartir experiencias, anécdotas, muchas cosas interesantes con
[00:00:20] anécdotas, muchas cosas interesantes con un personaje de muchísima trayectoria.
[00:00:23] un personaje de muchísima trayectoria. Yo considero una persona muy inteligente
[00:00:25] Yo considero una persona muy inteligente a la cual yo leo mucho, que es el
[00:00:28] a la cual yo leo mucho, que es el doctor, aunque no le gusta que le digan
[00:00:29] doctor, aunque no le gusta que le digan doctor, pero a César lo que es del sexa,
[00:00:32] doctor, pero a César lo que es del sexa, el doctor Matías Berman. Bienvenido,
[00:00:35] el doctor Matías Berman. Bienvenido, doctor, un placer tenerte aquí en el
[00:00:37] doctor, un placer tenerte aquí en el canal.
[00:00:38] canal. Muchas [risas] gracias, muchísimas
[00:00:39] Muchas [risas] gracias, muchísimas gracias. Super contento de estar acá.
[00:00:42] gracias. Super contento de estar acá. El doctor Matías Berman es uno de los
[00:00:44] El doctor Matías Berman es uno de los que está implicado en el programa BL
[00:00:46] que está implicado en el programa BL F90, un conocido programa de evaluación
[00:00:49] F90, un conocido programa de evaluación genética que se desarrolló en la
[00:00:51] genética que se desarrolló en la Universidad de Georgia con puro genio
[00:00:54] Universidad de Georgia con puro genio Ignaci Mictal, Daniela Laurenco, aquí
[00:00:57] Ignaci Mictal, Daniela Laurenco, aquí Matías presente,
[00:00:59] Matías presente, creo que también estaba ahí Andrés
[00:01:00] creo que también estaba ahí Andrés Legarra, Ignacio Aguilar, un poco de
[00:01:03] Legarra, Ignacio Aguilar, un poco de superdotados de genio que están ahí.
[00:01:06] superdotados de genio que están ahí. Bueno, y aquí tenemos uno de los
[00:01:09] Bueno, y aquí tenemos uno de los implicados en ese programa de evaluación
[00:01:11] implicados en ese programa de evaluación genética y hoy venimos a hablar un poco
[00:01:14] genética y hoy venimos a hablar un poco de evaluaciones genéticas y evaluaciones
[00:01:16] de evaluaciones genéticas y evaluaciones genómicas. Sé que en el canal hemos
[00:01:18] genómicas. Sé que en el canal hemos hablado poco de evaluación genómica. Si
[00:01:20] hablado poco de evaluación genómica. Si tenemos algunos videos con algunas
[00:01:22] tenemos algunos videos con algunas personas hablando del tema, pero hoy
[00:01:24] personas hablando del tema, pero hoy toca otra vez ese tema que tanto me lo
[00:01:26] toca otra vez ese tema que tanto me lo han pedido ustedes mis seguidores. Así
[00:01:28] han pedido ustedes mis seguidores. Así que volvemos a hablar de de estos
[00:01:29] que volvemos a hablar de de estos tópicos. Doctor, para comenzar este,
[00:01:32] tópicos. Doctor, para comenzar este, ¿qué me puede decir de las evaluaciones
[00:01:34] ¿qué me puede decir de las evaluaciones genéticas? las evaluaciones genómicas,
[00:01:36] genéticas? las evaluaciones genómicas, ¿qué sirven? ¿En qué se diferencian?
[00:01:38] ¿qué sirven? ¿En qué se diferencian? ¿Cuál es el punto crítico en ese aspecto
[00:01:40] ¿Cuál es el punto crítico en ese aspecto de las evaluaciones genéticas y
[00:01:42] de las evaluaciones genéticas y genómicas?
[00:01:42] genómicas? Eh, antes de responderte, quiero
[00:01:44] Eh, antes de responderte, quiero completar, por favor, la lista de
[00:01:46] completar, por favor, la lista de nombres que contribuyeron al BLF90
[00:01:49] nombres que contribuyeron al BLF90 porque somos muchos más que esos. Está
[00:01:51] porque somos muchos más que esos. Está Yogo Zuruta, Yutakaca Masuda, Miguel
[00:01:54] Yogo Zuruta, Yutakaca Masuda, Miguel Pérez Encicio, Mauricio Elso, Juan Pablo
[00:01:57] Pérez Encicio, Mauricio Elso, Juan Pablo Sánchez, creo que Olga Rabañolo tuvo
[00:01:59] Sánchez, creo que Olga Rabañolo tuvo algo, Vincent Taruá, eh Nicolas Gengler
[00:02:04] algo, Vincent Taruá, eh Nicolas Gengler puede ser. Entonces es una colaboración
[00:02:06] puede ser. Entonces es una colaboración Tom Druet muy muy larga y y me gustaría
[00:02:09] Tom Druet muy muy larga y y me gustaría mencionarlos también. Si puede repetir
[00:02:12] mencionarlos también. Si puede repetir la pregunta. Vamos a hablar de qué son
[00:02:14] la pregunta. Vamos a hablar de qué son las evaluaciones genéticas y las
[00:02:16] las evaluaciones genéticas y las evaluaciones genúmicas, para qué sirven,
[00:02:18] evaluaciones genúmicas, para qué sirven, qué se diferencia. Quiero un aspecto
[00:02:20] qué se diferencia. Quiero un aspecto general de de esos puntos, esos tópicos.
[00:02:22] general de de esos puntos, esos tópicos. Eh, todo lo que es el mejoramiento
[00:02:23] Eh, todo lo que es el mejoramiento genético sabemos que arrancó con el
[00:02:26] genético sabemos que arrancó con el paper de de Fisher a principios del año
[00:02:29] paper de de Fisher a principios del año 20 del siglo XX, perdón, cuando
[00:02:33] 20 del siglo XX, perdón, cuando cuando sentó las bases de lo que es el
[00:02:35] cuando sentó las bases de lo que es el mejoramiento de caracteres poligénicos y
[00:02:37] mejoramiento de caracteres poligénicos y después con muchas contribuciones, sobre
[00:02:39] después con muchas contribuciones, sobre todo el L de WR, eh se utilizó
[00:02:42] todo el L de WR, eh se utilizó información no solo de registro, sino de
[00:02:45] información no solo de registro, sino de genealogías para predecir eh lo que es
[00:02:49] genealogías para predecir eh lo que es el valor de cría, que el valor de cría
[00:02:51] el valor de cría, que el valor de cría es básicamente el mérito genético de los
[00:02:54] es básicamente el mérito genético de los animales.
[00:02:55] animales. Y después con varias metodologías
[00:02:58] Y después con varias metodologías estadísticas, BLAP, reml, muchas
[00:03:00] estadísticas, BLAP, reml, muchas contribuciones, se fueron armando lo que
[00:03:03] contribuciones, se fueron armando lo que fueron las evaluaciones genéticas, que
[00:03:05] fueron las evaluaciones genéticas, que es básicamente un sistema muy grande de
[00:03:09] es básicamente un sistema muy grande de eh de registro de datos, ¿sí? en el cual
[00:03:12] eh de registro de datos, ¿sí? en el cual esos datos se usan junto con información
[00:03:16] esos datos se usan junto con información de granja, de año, de estación, de
[00:03:19] de granja, de año, de estación, de ambiente y genealógica para producir ese
[00:03:22] ambiente y genealógica para producir ese valor de cría.
[00:03:24] valor de cría. Eh, en el año 2001, un paper muy
[00:03:26] Eh, en el año 2001, un paper muy importante de Mewisen, eh
[00:03:31] importante de Mewisen, eh hipotetizó que el uso de marcadores
[00:03:34] hipotetizó que el uso de marcadores genéticos podría aumentar muchísimo la
[00:03:37] genéticos podría aumentar muchísimo la precisión de esas evaluaciones genéticas
[00:03:40] precisión de esas evaluaciones genéticas eh y revolucionó eh lo que es la
[00:03:43] eh y revolucionó eh lo que es la disciplina porque todo el mundo intentó
[00:03:45] disciplina porque todo el mundo intentó ver cómo se pueden aplicar esos esa
[00:03:49] ver cómo se pueden aplicar esos esa información genómica para predecir
[00:03:51] información genómica para predecir valores de cría y después de más o menos
[00:03:53] valores de cría y después de más o menos 10, 20 años de investigación se llegó a
[00:03:56] 10, 20 años de investigación se llegó a una madurez en el cual lo las
[00:03:58] una madurez en el cual lo las evaluaciones genéticas clásicas que
[00:04:00] evaluaciones genéticas clásicas que consideran eh genealogía
[00:04:04] consideran eh genealogía y registros se le incorpora la genómica,
[00:04:08] y registros se le incorpora la genómica, ¿sí?, para predecir las relaciones entre
[00:04:11] ¿sí?, para predecir las relaciones entre los animales de una manera más precisa y
[00:04:12] los animales de una manera más precisa y de esa manera obtener evaluaciones
[00:04:15] de esa manera obtener evaluaciones mucho más e precisas.
[00:04:18] mucho más e precisas. Excelente, excelente, doctor. Hay unos
[00:04:20] Excelente, excelente, doctor. Hay unos puntos ahí que me gustaría discutir que
[00:04:22] puntos ahí que me gustaría discutir que estoy seguro que a todos los seguidores
[00:04:24] estoy seguro que a todos los seguidores les gustaría escuchar. Hay una parte
[00:04:27] les gustaría escuchar. Hay una parte fundamentada en la teoría de de modelos
[00:04:29] fundamentada en la teoría de de modelos mixto desarrollado por el doctor, creo
[00:04:31] mixto desarrollado por el doctor, creo que aquí todo el que trabaja en genética
[00:04:33] que aquí todo el que trabaja en genética lo conoce, el doctor Charles Royce
[00:04:34] lo conoce, el doctor Charles Royce Henderson, padre de la cría y
[00:04:36] Henderson, padre de la cría y mejoramiento genético animal moderno,
[00:04:39] mejoramiento genético animal moderno, que fue en la en el desarrollo de la
[00:04:42] que fue en la en el desarrollo de la matriz de parentesco, como tú muy bien
[00:04:43] matriz de parentesco, como tú muy bien dijiste, solo integraba el pedigri, es
[00:04:46] dijiste, solo integraba el pedigri, es decir, información genealógica. Después
[00:04:48] decir, información genealógica. Después cuando pasamos a evaluaciones genéticas,
[00:04:50] cuando pasamos a evaluaciones genéticas, creo que se llamaban, y usted me
[00:04:52] creo que se llamaban, y usted me corregirá, evaluaciones genéticas en
[00:04:53] corregirá, evaluaciones genéticas en múltiples pasos genómicas, perdón,
[00:04:55] múltiples pasos genómicas, perdón, evaluaciones genómica en múltiples
[00:04:57] evaluaciones genómica en múltiples pasos. Sí, que creo que en esa
[00:04:59] pasos. Sí, que creo que en esa metodología teníamos que genotipar a
[00:05:02] metodología teníamos que genotipar a todos los individuos del rebán, si no me
[00:05:05] todos los individuos del rebán, si no me equivoco. el salto fundamental de de esa
[00:05:09] equivoco. el salto fundamental de de esa evaluación genómica a una evaluación
[00:05:10] evaluación genómica a una evaluación genómica de un solo paso, que es el que
[00:05:13] genómica de un solo paso, que es el que todos conocemos, el single step, cómo se
[00:05:16] todos conocemos, el single step, cómo se dio, cómo se desarrolló, cuál es esa
[00:05:18] dio, cómo se desarrolló, cuál es esa diferenciación que se hizo para
[00:05:20] diferenciación que se hizo para diferenciar esas dos metodologías y para
[00:05:23] diferenciar esas dos metodologías y para poder optimizar costo en el caso de la
[00:05:24] poder optimizar costo en el caso de la evaluación genómica porque podíamos
[00:05:27] evaluación genómica porque podíamos tener evaluación genómica de animales
[00:05:29] tener evaluación genómica de animales que en verdad no están genotipeados,
[00:05:31] que en verdad no están genotipeados, simplemente conjugando esa información
[00:05:33] simplemente conjugando esa información de pedigri y genotipo. ¿Qué nos puede
[00:05:35] de pedigri y genotipo. ¿Qué nos puede decir un poco de eso?
[00:05:37] decir un poco de eso? Bien, es una buena pregunta. Las
[00:05:38] Bien, es una buena pregunta. Las evaluaciones de de múltiples pasos
[00:05:41] evaluaciones de de múltiples pasos básicamente lo que hacían era uno tenía
[00:05:44] básicamente lo que hacían era uno tenía una evaluación sin genómica para todos
[00:05:46] una evaluación sin genómica para todos los animales, obtenía información de esa
[00:05:49] los animales, obtenía información de esa evaluación que utilizaba como
[00:05:51] evaluación que utilizaba como pseudoregistros,
[00:05:53] pseudoregistros, ¿sí?, en una evaluación más reducida que
[00:05:55] ¿sí?, en una evaluación más reducida que era solo para los animales genotipados.
[00:05:58] era solo para los animales genotipados. Eh, eso tenía distintas desventajas,
[00:06:02] Eh, eso tenía distintas desventajas, ¿sí? sobre todo en eh modelos complejos.
[00:06:06] ¿sí? sobre todo en eh modelos complejos. ¿Por qué? Porque cómo crear un pseudoor
[00:06:09] ¿Por qué? Porque cómo crear un pseudoor registro para efectos maternos,
[00:06:11] registro para efectos maternos, regresiones aleatorias, etcétera,
[00:06:13] regresiones aleatorias, etcétera, etcétera, etcétera. Y que aparte la
[00:06:15] etcétera, etcétera. Y que aparte la información de los genotipados no se
[00:06:17] información de los genotipados no se propagaba a los no genotipados. Sí. Eh,
[00:06:21] propagaba a los no genotipados. Sí. Eh, sumado a dificultades técnicas que que
[00:06:23] sumado a dificultades técnicas que que hacían muy engorrosa la aplicación de de
[00:06:26] hacían muy engorrosa la aplicación de de esos métodos. Eh, y si bien yo en ese
[00:06:30] esos métodos. Eh, y si bien yo en ese momento claramente no estaba trabajando
[00:06:33] momento claramente no estaba trabajando porque en el 2009 tenía 14 años, eh,
[00:06:39] porque en el 2009 tenía 14 años, eh, dos grupos independientemente, el de
[00:06:41] dos grupos independientemente, el de Georgia con Ignacio Mistal, Andrés
[00:06:44] Georgia con Ignacio Mistal, Andrés Legarra, Nacho Aguilar y en Dinamarca,
[00:06:47] Legarra, Nacho Aguilar y en Dinamarca, Ole Christensen, desarrollaron
[00:06:50] Ole Christensen, desarrollaron eh
[00:06:51] eh o aplicaron una metodología estadística
[00:06:54] o aplicaron una metodología estadística para
[00:06:55] para que ambas fuentes de formación, tanto la
[00:06:58] que ambas fuentes de formación, tanto la genealógica como la genómica, puedan
[00:07:00] genealógica como la genómica, puedan combinarse en una única matriz de
[00:07:03] combinarse en una única matriz de parentesco. Sí. Eh, y por lo menos, a
[00:07:06] parentesco. Sí. Eh, y por lo menos, a ver, yo acá hablo como lector porque no
[00:07:08] ver, yo acá hablo como lector porque no participé de los desarrollos y cuando yo
[00:07:11] participé de los desarrollos y cuando yo empecé en el 2018 en este campo ya eso
[00:07:15] empecé en el 2018 en este campo ya eso estaba desarrollado.
[00:07:17] estaba desarrollado. Eh,
[00:07:19] Eh, quizás lo lindo, lo valioso de esta
[00:07:21] quizás lo lindo, lo valioso de esta metodología es que fue desarrollada por
[00:07:23] metodología es que fue desarrollada por dos grupos completamente separados y
[00:07:26] dos grupos completamente separados y siempre cuenta Andrés Ignaci
[00:07:30] siempre cuenta Andrés Ignaci fue una Gordon Conference o alguna
[00:07:32] fue una Gordon Conference o alguna conferencia o una Interv.
[00:07:34] conferencia o una Interv. que
[00:07:36] que iban a presentar lo mismo y no lo sabían
[00:07:38] iban a presentar lo mismo y no lo sabían y nada, debió haber sido una situación
[00:07:40] y nada, debió haber sido una situación muy divertida. Entonces, eh
[00:07:44] muy divertida. Entonces, eh siempre que se citan ambos trabajos se
[00:07:46] siempre que se citan ambos trabajos se citan juntos porque realmente
[00:07:48] citan juntos porque realmente se desarrollaron el mismo año, tienen
[00:07:51] se desarrollaron el mismo año, tienen casi la misma información. George ya lo
[00:07:53] casi la misma información. George ya lo desarrolló en dos papers separados. Sí,
[00:07:56] desarrolló en dos papers separados. Sí, porque como vos dijiste en en la matriz
[00:07:59] porque como vos dijiste en en la matriz de modelos mixtos se necesita la inversa
[00:08:01] de modelos mixtos se necesita la inversa de las relaciones, ¿no? No las
[00:08:03] de las relaciones, ¿no? No las relaciones per sé. Eh, Georgia lo hizo
[00:08:07] relaciones per sé. Eh, Georgia lo hizo en dos publicaciones en el 2009 y 2010 y
[00:08:10] en dos publicaciones en el 2009 y 2010 y Ole Christensen y y Morgens Lund lo
[00:08:12] Ole Christensen y y Morgens Lund lo hicieron en una sola en el 2010. Eh,
[00:08:15] hicieron en una sola en el 2010. Eh, pero el resto, esa yo creo que es la
[00:08:17] pero el resto, esa yo creo que es la historia. Hubieron muchos otros
[00:08:19] historia. Hubieron muchos otros desarrollos, ¿sí? Para poder aplicar
[00:08:22] desarrollos, ¿sí? Para poder aplicar esto al a los datos. eh
[00:08:25] esto al a los datos. eh a a datos reales y se siguen
[00:08:27] a a datos reales y se siguen desarrollando todavía cosas como
[00:08:30] desarrollando todavía cosas como metafundadores,
[00:08:32] metafundadores, eh cosas como modelos no lineales, aún
[00:08:34] eh cosas como modelos no lineales, aún todavía están en desarrollo, pero la la
[00:08:36] todavía están en desarrollo, pero la la tecnología ya está muy madura.
[00:08:37] tecnología ya está muy madura. Excelente, excelente. Sí, creo que es
[00:08:39] Excelente, excelente. Sí, creo que es una historia interesante. Creo que en
[00:08:41] una historia interesante. Creo que en algún momento escuché algo de eso del
[00:08:43] algún momento escuché algo de eso del doctor Andrés Legarra en una entrevista
[00:08:45] doctor Andrés Legarra en una entrevista que le hizo a Agustín Blasco en su
[00:08:46] que le hizo a Agustín Blasco en su programa. Creo que lo vi, creo que por
[00:08:49] programa. Creo que lo vi, creo que por encima nombró esa esa cuestión. Creo que
[00:08:52] encima nombró esa esa cuestión. Creo que también una ventaja del single, creo que
[00:08:54] también una ventaja del single, creo que estaremos de acuerdo este Matías, es que
[00:08:57] estaremos de acuerdo este Matías, es que es que se ahorran costos, ¿no? Porque si
[00:09:00] es que se ahorran costos, ¿no? Porque si no no tendríamos que genotipiar todo el
[00:09:03] no no tendríamos que genotipiar todo el rebaño completo, toda la población, sino
[00:09:06] rebaño completo, toda la población, sino solo una parte y usar la información de
[00:09:08] solo una parte y usar la información de pedir como información a priori para la
[00:09:10] pedir como información a priori para la información genómica o no es así
[00:09:13] información genómica o no es así en el múltiples pasos. Es decir, si en
[00:09:17] en el múltiples pasos. Es decir, si en el en la metodología de múltiples pasos
[00:09:20] el en la metodología de múltiples pasos uno quiere un valor de cría genómico
[00:09:22] uno quiere un valor de cría genómico para todos los animales, sí tienen que
[00:09:25] para todos los animales, sí tienen que estar eh genotipados porque no existe
[00:09:28] estar eh genotipados porque no existe esa propagación. Ahora bien, por
[00:09:30] esa propagación. Ahora bien, por ejemplo, en cuando en Estados Unidos se
[00:09:33] ejemplo, en cuando en Estados Unidos se desarrolló esto, eh el ganado lechero
[00:09:36] desarrolló esto, eh el ganado lechero tenía
[00:09:38] tenía millones de animales y solo unos pocos
[00:09:41] millones de animales y solo unos pocos miles genotipados al principio y igual
[00:09:44] miles genotipados al principio y igual se podía hacer. la evaluación. La
[00:09:47] se podía hacer. la evaluación. La ventaja del single step es propagación,
[00:09:50] ventaja del single step es propagación, ¿sí? y
[00:09:53] ¿sí? y la facilidad que tiene eh para ser
[00:09:57] la facilidad que tiene eh para ser aplicado a modelos más complejos, como
[00:09:59] aplicado a modelos más complejos, como ya mencioné, efectos maternos, eh
[00:10:01] ya mencioné, efectos maternos, eh modelos no lineales, eh regresiones
[00:10:04] modelos no lineales, eh regresiones aleatorias,
[00:10:06] aleatorias, eh
[00:10:08] eh y que aparte es mucho más fácil de
[00:10:09] y que aparte es mucho más fácil de programar, de aplicar, de explicar
[00:10:13] programar, de aplicar, de explicar también.
[00:10:15] también. Excelente, excelente. Hay una cuestión
[00:10:17] Excelente, excelente. Hay una cuestión que que siempre pregunto, pero no por
[00:10:19] que que siempre pregunto, pero no por cuestión de debates, porque siempre aquí
[00:10:21] cuestión de debates, porque siempre aquí los seguidores me lo han preguntado en
[00:10:22] los seguidores me lo han preguntado en algunos casos, es sobre el yo sé que el
[00:10:25] algunos casos, es sobre el yo sé que el single est entendido que estas
[00:10:27] single est entendido que estas evaluaciones genómicas nacieron desde un
[00:10:29] evaluaciones genómicas nacieron desde un punto de vista valleciano porque
[00:10:30] punto de vista valleciano porque anteriormente era lo que se podía hacer,
[00:10:33] anteriormente era lo que se podía hacer, pero hoy en día ya se puede hacer desde
[00:10:35] pero hoy en día ya se puede hacer desde un punto de vista entre comillas
[00:10:37] un punto de vista entre comillas frecuentista usando el remel. Bueno, en
[00:10:39] frecuentista usando el remel. Bueno, en este caso sería un CCG REMEL, este, y ya
[00:10:43] este caso sería un CCG REMEL, este, y ya se pueden hacer de las dos maneras.
[00:10:46] se pueden hacer de las dos maneras. Hablamos de evaluaciones genómicas
[00:10:47] Hablamos de evaluaciones genómicas porque sabemos que las evaluaciones
[00:10:48] porque sabemos que las evaluaciones genéticas con Pedri sí se pueden hacer
[00:10:50] genéticas con Pedri sí se pueden hacer de las dos formas de hace mucho tiempo.
[00:10:53] de las dos formas de hace mucho tiempo. Desde estos puntos de vista, ¿cuál es la
[00:10:56] Desde estos puntos de vista, ¿cuál es la más eficiente, digamos, en modelos de
[00:10:57] más eficiente, digamos, en modelos de evaluación genética convencionales?
[00:10:59] evaluación genética convencionales? ¿Cuál es la que ahorra más cómputo?
[00:11:01] ¿Cuál es la que ahorra más cómputo? Porque yo tengo entendido, aunque nunca
[00:11:04] Porque yo tengo entendido, aunque nunca lo he corrido este en evaluación, nunca
[00:11:06] lo he corrido este en evaluación, nunca las he hecho, que si en como en genética
[00:11:09] las he hecho, que si en como en genética tenemos muchos datos, o sea, tenemos
[00:11:11] tenemos muchos datos, o sea, tenemos este grandes, masivas cantidades de
[00:11:13] este grandes, masivas cantidades de datos, los parámetros están por ahí.
[00:11:15] datos, los parámetros están por ahí. Incluso hay unos paper que indican que
[00:11:18] Incluso hay unos paper que indican que si tú tienes muchos muchos datos,
[00:11:20] si tú tienes muchos muchos datos, incluso las evaluaciones genéticas con
[00:11:21] incluso las evaluaciones genéticas con pedigri estarán por ahí, se van a
[00:11:23] pedigri estarán por ahí, se van a aparecer los parámetros. Entonces,
[00:11:25] aparecer los parámetros. Entonces, quiero que me digas, o sea, más o menos
[00:11:28] quiero que me digas, o sea, más o menos desde un punto de vista valleciano, un
[00:11:30] desde un punto de vista valleciano, un punto de vista frecuentista, o sea, ¿qué
[00:11:31] punto de vista frecuentista, o sea, ¿qué es lo que conviene más? Yo sé que el
[00:11:33] es lo que conviene más? Yo sé que el valleismo tiene algunas ventajadas, pero
[00:11:34] valleismo tiene algunas ventajadas, pero sería bueno que que usted nos explicara
[00:11:36] sería bueno que que usted nos explicara eso.
[00:11:38] eso. Eh,
[00:11:39] Eh, bien, primero, las evaluaciones
[00:11:40] bien, primero, las evaluaciones genéticas tienen muchos pasos o muchas
[00:11:43] genéticas tienen muchos pasos o muchas cosas que necesitan eh ser llevadas a
[00:11:46] cosas que necesitan eh ser llevadas a cabo. Sí. Eh, por lo general, en la gran
[00:11:50] cabo. Sí. Eh, por lo general, en la gran mayoría de los casos, eh, durante un
[00:11:53] mayoría de los casos, eh, durante un cierto periodo de tiempo se asumen
[00:11:54] cierto periodo de tiempo se asumen componentes de varianzas fijos, ¿sí? Y
[00:11:58] componentes de varianzas fijos, ¿sí? Y solamente se calculan valores de cría y
[00:12:01] solamente se calculan valores de cría y eh desde el punto de vista frecuentista
[00:12:04] eh desde el punto de vista frecuentista efectos fijos. Desde el punto de vista
[00:12:06] efectos fijos. Desde el punto de vista valleciano lo que serían es el ectos
[00:12:11] valleciano lo que serían es el ectos con una prior plana. Sí, flat prior. Eh,
[00:12:18] con una prior plana. Sí, flat prior. Eh, bien, para la parte de componentes de
[00:12:19] bien, para la parte de componentes de varianzas depende mucho del modelo, ¿sí?
[00:12:23] varianzas depende mucho del modelo, ¿sí? Eh, un modelo complejo
[00:12:26] Eh, un modelo complejo siempre quizás la estimación valleciana
[00:12:28] siempre quizás la estimación valleciana ayuda mucho, sí,
[00:12:32] ayuda mucho, sí, pero la estimación frecuentista mediante
[00:12:34] pero la estimación frecuentista mediante REML es mucho más rápida y requiere
[00:12:37] REML es mucho más rápida y requiere menos conocimiento, menos experiencia eh
[00:12:40] menos conocimiento, menos experiencia eh y menos input del usuario. ¿Por qué?
[00:12:43] y menos input del usuario. ¿Por qué? Porque uno corre un remel, converge y
[00:12:44] Porque uno corre un remel, converge y está. Eh, con un GIF sampler, por
[00:12:47] está. Eh, con un GIF sampler, por ejemplo, uno tiene que ver, okay,
[00:12:48] ejemplo, uno tiene que ver, okay, cuántas muestras, si convirgió la cadena
[00:12:51] cuántas muestras, si convirgió la cadena para todos los parámetros que tengo, eh,
[00:12:54] para todos los parámetros que tengo, eh, voy a usar la moda, voy a usar la media,
[00:12:57] voy a usar la moda, voy a usar la media, qué vernin voy a usar, es más casero,
[00:13:00] qué vernin voy a usar, es más casero, sí, pero en un modelo muy complejo, el
[00:13:04] sí, pero en un modelo muy complejo, el remil puede funcionar peor que el GISBS.
[00:13:06] remil puede funcionar peor que el GISBS. Entonces, en ese caso, quizás uno
[00:13:07] Entonces, en ese caso, quizás uno prefiere algo valleciano. Sí.
[00:13:11] prefiere algo valleciano. Sí. Eh,
[00:13:12] Eh, después hay ventajas o ventajas
[00:13:14] después hay ventajas o ventajas computacionales. Sí, para modelos muy
[00:13:16] computacionales. Sí, para modelos muy grandes, los vallecianos por la cantidad
[00:13:18] grandes, los vallecianos por la cantidad de muestras y autocorrelación entre
[00:13:20] de muestras y autocorrelación entre muestras pueden necesitar muchas
[00:13:21] muestras pueden necesitar muchas muestras. Sí, lo cual puede llevar meses
[00:13:25] muestras. Sí, lo cual puede llevar meses quizás. eh y desarrollos recientes en
[00:13:29] quizás. eh y desarrollos recientes en métodos frecuentistas, como por ejemplo
[00:13:31] métodos frecuentistas, como por ejemplo el Montecarlo REML, que es un REML donde
[00:13:35] el Montecarlo REML, que es un REML donde la inversión de de la matriz de
[00:13:38] la inversión de de la matriz de coeficientes es reemplazada por una
[00:13:40] coeficientes es reemplazada por una serie de simulaciones,
[00:13:42] serie de simulaciones, puede pasar ese tiempo de cómputo de
[00:13:44] puede pasar ese tiempo de cómputo de semanas a un par de horas
[00:13:47] semanas a un par de horas y entonces es una cuestión de tiempos.
[00:13:50] y entonces es una cuestión de tiempos. Ahora bien, ¿qué pasa cuando uno ya
[00:13:51] Ahora bien, ¿qué pasa cuando uno ya tiene los componentes de varianza y los
[00:13:54] tiene los componentes de varianza y los pasa a utilizar rutinariamente?
[00:13:57] pasa a utilizar rutinariamente? Ahí las evaluaciones genéticas utilizan
[00:14:00] Ahí las evaluaciones genéticas utilizan blap frecuentista.
[00:14:02] blap frecuentista. Sí. Eh, ¿por qué utilizan blap
[00:14:05] Sí. Eh, ¿por qué utilizan blap frecuentista? Primero, por velocidad.
[00:14:09] frecuentista? Primero, por velocidad. Sí, es mucho más rápido. Eh,
[00:14:13] Sí, es mucho más rápido. Eh, segundo,
[00:14:15] segundo, porque
[00:14:17] porque uno toca una tecla y siempre obtiene
[00:14:18] uno toca una tecla y siempre obtiene casi el mismo resultado con los métodos
[00:14:20] casi el mismo resultado con los métodos vallecianos, no siempre, porque depende
[00:14:22] vallecianos, no siempre, porque depende del generador de números aleatorios, de
[00:14:24] del generador de números aleatorios, de la cantidad de muestras, eh del burning
[00:14:27] la cantidad de muestras, eh del burning que usemos. Entonces, uno en las
[00:14:30] que usemos. Entonces, uno en las evaluaciones genéticas requiere una
[00:14:31] evaluaciones genéticas requiere una cierta estabilidad numérica,
[00:14:34] cierta estabilidad numérica, ¿sí?, eh y temporal que te la suelen dar
[00:14:38] ¿sí?, eh y temporal que te la suelen dar más esos métodos eh frecuentistas.
[00:14:43] más esos métodos eh frecuentistas. Sumado a eso, sí, eh
[00:14:47] Sumado a eso, sí, eh el uso de métodos frecuentistas
[00:14:49] el uso de métodos frecuentistas optimizados, por ejemplo, iteración en
[00:14:50] optimizados, por ejemplo, iteración en datos, donde no se construye la matriz
[00:14:52] datos, donde no se construye la matriz de modelos mixtos, sino que se hacen
[00:14:54] de modelos mixtos, sino que se hacen multiplicaciones
[00:14:56] multiplicaciones sucesivas, eh solamente leyendo los
[00:14:59] sucesivas, eh solamente leyendo los datos y y el pedigri, bueno, hacen que
[00:15:03] datos y y el pedigri, bueno, hacen que los requerimientos de memoria sean mucho
[00:15:04] los requerimientos de memoria sean mucho menor que para los métodos vallecianos.
[00:15:08] menor que para los métodos vallecianos. Ahora bien, si nos podemos ponemos una
[00:15:10] Ahora bien, si nos podemos ponemos una interpretación estadística, el blap es
[00:15:12] interpretación estadística, el blap es un máxima un máximo posteriori, ¿no?,
[00:15:16] un máxima un máximo posteriori, ¿no?, con determinadas priors. Entonces, a fin
[00:15:18] con determinadas priors. Entonces, a fin de cuentas, la interpretación de los
[00:15:20] de cuentas, la interpretación de los galeros de cría es muy similar,
[00:15:22] galeros de cría es muy similar, pero desde el punto de vista práctico,
[00:15:24] pero desde el punto de vista práctico, para para la rutina se prefieren en
[00:15:26] para para la rutina se prefieren en general los métodos frecuentistas
[00:15:28] general los métodos frecuentistas basados en blap y el método iterativo
[00:15:32] basados en blap y el método iterativo que se llama de solución de sistemas que
[00:15:34] que se llama de solución de sistemas que se llama eh de gradientes preconjugados.
[00:15:42] Excelente, excelente. Eso que dijiste de último gradiente es preconjugado. Me
[00:15:43] último gradiente es preconjugado. Me acuerdo cuando me hiciste
[00:15:46] acuerdo cuando me hiciste dar ese infierno. Bueno, [risas]
[00:15:49] dar ese infierno. Bueno, [risas] ya eso quedó en el pasado.
[00:15:52] ya eso quedó en el pasado. Matías, a veces tengo, se me olvida que
[00:15:54] Matías, a veces tengo, se me olvida que no puedo llamarte do no te gusta, pero
[00:15:57] no puedo llamarte do no te gusta, pero se me quedan a mí
[00:15:59] se me quedan a mí y
[00:16:00] y no pasa nada.
[00:16:02] no pasa nada. En fin, es interesante esto que que
[00:16:04] En fin, es interesante esto que que mencionaste sobre B y Rel. Bueno, al
[00:16:07] mencionaste sobre B y Rel. Bueno, al final yo siempre creo que si si si
[00:16:10] final yo siempre creo que si si si tienes la capacidad de correrlo y un
[00:16:13] tienes la capacidad de correrlo y un modelo no tan complejo, no un modelo
[00:16:15] modelo no tan complejo, no un modelo lineal generalizado, un tresor o una
[00:16:17] lineal generalizado, un tresor o una cosa de estas pues con variable no
[00:16:20] cosa de estas pues con variable no normal, o sea, no gauciana, creo que
[00:16:22] normal, o sea, no gauciana, creo que podré usar el que tú quieras en en el
[00:16:24] podré usar el que tú quieras en en el canal de estadísticas,
[00:16:26] canal de estadísticas, este siempre explicamos los métodos
[00:16:27] este siempre explicamos los métodos frecuentistos, pero si tocamos algunos
[00:16:29] frecuentistos, pero si tocamos algunos casos, los vallecianos no son
[00:16:31] casos, los vallecianos no son desconocidos para mí, no, pero no los
[00:16:33] desconocidos para mí, no, pero no los hemos abordado este en profundidad. Y
[00:16:37] hemos abordado este en profundidad. Y siempre me lo han preguntado algunos
[00:16:39] siempre me lo han preguntado algunos seguidores que me escriben este al
[00:16:41] seguidores que me escriben este al privado, pues, ¿y para cuándo lo de los
[00:16:43] privado, pues, ¿y para cuándo lo de los valleciños? Bueno, pronto, todavía no.
[00:16:46] valleciños? Bueno, pronto, todavía no. Hay una cuestión también que es
[00:16:49] Hay una cuestión también que es interesante que esa es una pregunta, no
[00:16:51] interesante que esa es una pregunta, no de los seguidores, voy a confesar que es
[00:16:52] de los seguidores, voy a confesar que es mía. El proceso de inversión de la
[00:16:55] mía. El proceso de inversión de la matriz conjugada, o sea, de la matriz H,
[00:16:57] matriz conjugada, o sea, de la matriz H, para mí eso debía haber sido un reto
[00:16:59] para mí eso debía haber sido un reto porque como tú bien dijiste, no
[00:17:02] porque como tú bien dijiste, no necesitamos la matriz, sino su inversa.
[00:17:04] necesitamos la matriz, sino su inversa. Y creo que ese proceso es
[00:17:05] Y creo que ese proceso es computacionalmente costoso y lo sé por
[00:17:08] computacionalmente costoso y lo sé por experiencia, o sea, porque y no hablando
[00:17:10] experiencia, o sea, porque y no hablando de H, sino hablando de una matriz de
[00:17:11] de H, sino hablando de una matriz de parentesco, una matriz A clásica.
[00:17:14] parentesco, una matriz A clásica. Entonces, bueno, tuvimos que programar
[00:17:15] Entonces, bueno, tuvimos que programar esos métodos de gender sin usar ninguna
[00:17:17] esos métodos de gender sin usar ninguna librería, pues desde cero, pero bueno,
[00:17:20] librería, pues desde cero, pero bueno, no fue bien. Ahora en H cuando veo la
[00:17:21] no fue bien. Ahora en H cuando veo la estructura, este, veo que obviamente fue
[00:17:24] estructura, este, veo que obviamente fue un reto, o sea, más o menos, ¿cómo cómo
[00:17:26] un reto, o sea, más o menos, ¿cómo cómo se maneja ese procedimiento?
[00:17:29] se maneja ese procedimiento? Eh, bien, de vuelta, la parte histórica
[00:17:31] Eh, bien, de vuelta, la parte histórica yo la puedo contar porque me la
[00:17:33] yo la puedo contar porque me la contaron. No la viví y porque veo código
[00:17:35] contaron. No la viví y porque veo código y leo papers. Eh, en 2009,
[00:17:40] y leo papers. Eh, en 2009, Andrés, Ignaci y Ignacio
[00:17:44] Andrés, Ignaci y Ignacio derivaron H, pero como vos dijiste se
[00:17:47] derivaron H, pero como vos dijiste se necesita H inversa. Sí,
[00:17:51] necesita H inversa. Sí, para estos iteraciones en datos,
[00:17:53] para estos iteraciones en datos, entonces ellos propusieron utilizar H
[00:17:55] entonces ellos propusieron utilizar H con unas ecuaciones de modelo mixto
[00:17:57] con unas ecuaciones de modelo mixto especiales y un solver especial que
[00:17:59] especiales y un solver especial que funcionaba bastante mal. Sí.
[00:18:02] funcionaba bastante mal. Sí. Una vez que se descubrió la estructura
[00:18:04] Una vez que se descubrió la estructura de H inversa, que es mucho más sencilla
[00:18:06] de H inversa, que es mucho más sencilla que la de H, ¿sí? H inversa se compone
[00:18:09] que la de H, ¿sí? H inversa se compone básicamente de tres cosas, ¿sí? La
[00:18:11] básicamente de tres cosas, ¿sí? La inversa del pedigrí, de la relación de
[00:18:14] inversa del pedigrí, de la relación de pedigrí que se obtiene con las reglas de
[00:18:16] pedigrí que se obtiene con las reglas de Henderson, como vos dijiste, la inversa
[00:18:19] Henderson, como vos dijiste, la inversa de las relaciones genómicas de G y la
[00:18:22] de las relaciones genómicas de G y la inversa de la relación de pedigrí entre
[00:18:25] inversa de la relación de pedigrí entre los animales genotipados, que eso sería
[00:18:28] los animales genotipados, que eso sería A2 inversa. ¿Sí?
[00:18:30] A2 inversa. ¿Sí? Y de vuelta hago distinción en eh
[00:18:36] Y de vuelta hago distinción en eh de dos procesos. ¿Qué pasa para
[00:18:37] de dos procesos. ¿Qué pasa para componentes de varianza en remel?
[00:18:39] componentes de varianza en remel? Nosotros necesitamos invertir la matriz
[00:18:41] Nosotros necesitamos invertir la matriz de ecuaciones de modelo mixto. Entonces,
[00:18:44] de ecuaciones de modelo mixto. Entonces, en ese caso, H inversa se crea
[00:18:46] en ese caso, H inversa se crea explícitamente, ¿sí?, con esos tres
[00:18:49] explícitamente, ¿sí?, con esos tres bloques, eh, y después se manda todo a
[00:18:53] bloques, eh, y después se manda todo a una inversión rala. ¿Sí? ¿Qué quiere
[00:18:55] una inversión rala. ¿Sí? ¿Qué quiere decir rala? Que tiene muchos ceros y
[00:18:58] decir rala? Que tiene muchos ceros y bloques de no ceros. Sí. Las relaciones
[00:19:00] bloques de no ceros. Sí. Las relaciones de pedigrí en su inversa son ralas, las
[00:19:03] de pedigrí en su inversa son ralas, las genómicas no. Eh,
[00:19:07] genómicas no. Eh, eso es en componentes de variancia, o
[00:19:08] eso es en componentes de variancia, o sea, en componentes de varianza la
[00:19:10] sea, en componentes de varianza la inversión tiene que ser a fuerza bruta y
[00:19:12] inversión tiene que ser a fuerza bruta y y
[00:19:14] y hay otras maneras, pero bueno, se está
[00:19:16] hay otras maneras, pero bueno, se está limitado por eso. Ahora, si lo único que
[00:19:18] limitado por eso. Ahora, si lo único que nos interesa son valores de cría,
[00:19:21] nos interesa son valores de cría, eh
[00:19:23] eh utilizamos solvers iterativos, ¿sí? Y el
[00:19:27] utilizamos solvers iterativos, ¿sí? Y el solve iterativo no requiere invertir una
[00:19:29] solve iterativo no requiere invertir una matriz de modelos mixtos, sino requiere
[00:19:31] matriz de modelos mixtos, sino requiere multiplicar esa matriz por un vector.
[00:19:35] multiplicar esa matriz por un vector. Entonces, tenemos los tres componentes
[00:19:36] Entonces, tenemos los tres componentes de H inversa, que son A inversa, las de
[00:19:39] de H inversa, que son A inversa, las de pedigri. Bueno, multiplicarlos por un
[00:19:41] pedigri. Bueno, multiplicarlos por un vector es muy fácil, es una inversa
[00:19:42] vector es muy fácil, es una inversa rara. Tenemos
[00:19:46] rara. Tenemos G inversa. Bueno, si tenemos pocos
[00:19:47] G inversa. Bueno, si tenemos pocos animales, por ejemplo, 30.000, 50.000,
[00:19:50] animales, por ejemplo, 30.000, 50.000, podemos invertir G y multiplicarlas. Sí.
[00:19:53] podemos invertir G y multiplicarlas. Sí. Eh, ¿qué pasa si tenemos más? Hay
[00:19:55] Eh, ¿qué pasa si tenemos más? Hay distintas metodologías. Eh, en Georgia
[00:19:58] distintas metodologías. Eh, en Georgia se usa mucho lo que se llama el
[00:20:00] se usa mucho lo que se llama el algoritmo de, lo oigo en inglés,
[00:20:02] algoritmo de, lo oigo en inglés, algoritm for proven, APY.
[00:20:05] algoritm for proven, APY. Eh, esa amantisari en en Finlandia
[00:20:08] Eh, esa amantisari en en Finlandia desarrolló algo que llama GT Blue que
[00:20:11] desarrolló algo que llama GT Blue que utiliza la identidad de Woodbury, una
[00:20:14] utiliza la identidad de Woodbury, una multiplicación de matrices y Sentin Leu
[00:20:17] multiplicación de matrices y Sentin Leu y bueno, los investigadores de Holanda
[00:20:20] y bueno, los investigadores de Holanda desarrollaron el single step snipab que
[00:20:23] desarrollaron el single step snipab que evita la inversión de G expandiendo el
[00:20:25] evita la inversión de G expandiendo el sistema, estimando al mismo tiempo
[00:20:27] sistema, estimando al mismo tiempo valores de cría y efectos de marcadores.
[00:20:31] valores de cría y efectos de marcadores. Y nos queda una partecita que es la de
[00:20:32] Y nos queda una partecita que es la de A2 inversa que eh por reglas de matrices
[00:20:35] A2 inversa que eh por reglas de matrices particionadas puede ser multiplicada muy
[00:20:37] particionadas puede ser multiplicada muy fácil. Entonces, si tenemos componentes
[00:20:39] fácil. Entonces, si tenemos componentes de varianza, tenemos que invertir
[00:20:42] de varianza, tenemos que invertir eh salvo que usemos lo que mencioné
[00:20:45] eh salvo que usemos lo que mencioné antes el Montecarlos Renel, pero tenemos
[00:20:47] antes el Montecarlos Renel, pero tenemos que invertir. Si tenemos que calcular
[00:20:49] que invertir. Si tenemos que calcular valores de cría, tenemos que multiplicar
[00:20:50] valores de cría, tenemos que multiplicar por un vector y eso lo podemos hacer
[00:20:52] por un vector y eso lo podemos hacer para millones y millones de animales
[00:20:54] para millones y millones de animales genotipados
[00:20:56] genotipados e con básicamente tres metodologías.
[00:21:01] e con básicamente tres metodologías. Excelente, excelente. Menos mal que me
[00:21:03] Excelente, excelente. Menos mal que me calaste la inquietud porque lo dejé si
[00:21:05] calaste la inquietud porque lo dejé si me parecía difícil, ¿no? Porque la
[00:21:09] me parecía difícil, ¿no? Porque la inversión creo que tiene antes, bueno,
[00:21:12] inversión creo que tiene antes, bueno, yo tengo una computadora viejita, no
[00:21:14] yo tengo una computadora viejita, no quiero engañar aquí
[00:21:16] quiero engañar aquí que tenemos, bueno, por lo menos de mi
[00:21:18] que tenemos, bueno, por lo menos de mi parte una supercutadora ni ni nada de
[00:21:20] parte una supercutadora ni ni nada de eso, ¿no? Pero bueno, sé más o menos, no
[00:21:23] eso, ¿no? Pero bueno, sé más o menos, no como el doctor aquí porque ya otra liga
[00:21:26] como el doctor aquí porque ya otra liga nivel, pero sé algo de programar blop y
[00:21:29] nivel, pero sé algo de programar blop y componentes de varianza y remel y cosas
[00:21:30] componentes de varianza y remel y cosas de estas, ¿no? Entonces sí me tenía esa
[00:21:34] de estas, ¿no? Entonces sí me tenía esa duda importante. Doctor, para terminar
[00:21:36] duda importante. Doctor, para terminar hay un punto importante en en quiero que
[00:21:39] hay un punto importante en en quiero que nos cuentes en qué estás trabajando hoy
[00:21:41] nos cuentes en qué estás trabajando hoy en día, lo más reciente, qué es lo que
[00:21:43] en día, lo más reciente, qué es lo que se viene en la investigación de
[00:21:45] se viene en la investigación de mejoramiento genético animal en genética
[00:21:46] mejoramiento genético animal en genética cuantitativa. ¿Qué nos puedes hablar de
[00:21:48] cuantitativa. ¿Qué nos puedes hablar de de tus últimos hallazgos, tus últimas
[00:21:50] de tus últimos hallazgos, tus últimas investigaciones?
[00:21:52] investigaciones? Yo creo que lo lindo de este campo es
[00:21:54] Yo creo que lo lindo de este campo es que hay mucho para hacer y mucho
[00:21:56] que hay mucho para hacer y mucho distinto. Sí. Eh,
[00:22:02] distinto. Sí. Eh, tenemos desde investigación puramente
[00:22:04] tenemos desde investigación puramente estadística o o computacional o o de
[00:22:07] estadística o o computacional o o de desarrollo de modelos, que es más lo que
[00:22:09] desarrollo de modelos, que es más lo que yo hago, hasta cosas muy biológicas como
[00:22:13] yo hago, hasta cosas muy biológicas como eh utilización de ómica,
[00:22:15] eh utilización de ómica, transcriptómica,
[00:22:17] transcriptómica, eh o anotación de genomas. eh
[00:22:21] eh o anotación de genomas. eh construcción de genomas, también de
[00:22:23] construcción de genomas, también de genomas de referencia,
[00:22:25] genomas de referencia, eh cosas para evaluaciones genéticas muy
[00:22:28] eh cosas para evaluaciones genéticas muy aplicadas. Entonces, hay un abanico muy
[00:22:30] aplicadas. Entonces, hay un abanico muy muy amplio. Lo que yo me dedico más es a
[00:22:32] muy amplio. Lo que yo me dedico más es a la metodología y lo último que hicimos
[00:22:35] la metodología y lo último que hicimos fue extender el modelo de umbral, que es
[00:22:38] fue extender el modelo de umbral, que es para caracteres categóricos, a múltiples
[00:22:42] para caracteres categóricos, a múltiples características. hace antes no se podía,
[00:22:46] características. hace antes no se podía, no existía una contraparte, entre
[00:22:48] no existía una contraparte, entre comillas, frecuentista del del GIF
[00:22:50] comillas, frecuentista del del GIF Sampler para tener eh modelos
[00:22:52] Sampler para tener eh modelos multicácteres para carácteres
[00:22:54] multicácteres para carácteres categóricos. Eh, entonces no se podía
[00:22:56] categóricos. Eh, entonces no se podía usar en evaluación porque por motivos
[00:22:59] usar en evaluación porque por motivos computacionales. Y entonces lo que yo
[00:23:01] computacionales. Y entonces lo que yo hice junto con Andrés, con Daniela, con
[00:23:03] hice junto con Andrés, con Daniela, con Ignacia también es desarrollar,
[00:23:05] Ignacia también es desarrollar, extenderlo para que sea múltiples
[00:23:07] extenderlo para que sea múltiples características.
[00:23:09] características. Esto se publicó hace poquito, hace una
[00:23:11] Esto se publicó hace poquito, hace una semana más o menos.
[00:23:13] semana más o menos. Y yo no lo he leído. Tenemos que estar
[00:23:15] Y yo no lo he leído. Tenemos que estar pendiente [risas] en la revista. No sé
[00:23:18] pendiente [risas] en la revista. No sé dónde está. En el
[00:23:20] dónde está. En el Mucho en dónde?
[00:23:22] Mucho en dónde? En Genetics.
[00:23:23] En Genetics. Ah, en Genetic. Ah, no, sí lo vi. Sí lo
[00:23:25] Ah, en Genetic. Ah, no, sí lo vi. Sí lo vi, pero no lo he leído. Correcto. Sí,
[00:23:27] vi, pero no lo he leído. Correcto. Sí, se salió hace poquito. Tiene razón. El
[00:23:30] se salió hace poquito. Tiene razón. El el último que leí fue uno que es
[00:23:33] el último que leí fue uno que es presidente sobre remer usado en
[00:23:36] presidente sobre remer usado en evaluaciones genómicas masivas, ¿no?
[00:23:38] evaluaciones genómicas masivas, ¿no? Sí, eso es lo que yo mencioné, que es el
[00:23:41] Sí, eso es lo que yo mencioné, que es el Montecarlo Remi,
[00:23:43] Montecarlo Remi, eh, que en realidad el desarrollo se
[00:23:45] eh, que en realidad el desarrollo se remonta, creo que sí, a los 90 con
[00:23:49] remonta, creo que sí, a los 90 con Alberto García Cortés, eh,
[00:23:52] Alberto García Cortés, eh, también tratando de evitar esta inversa,
[00:23:55] también tratando de evitar esta inversa, fue retomado por Robin Thompson.
[00:24:00] fue retomado por Robin Thompson. y no me acuerdo que otros autores en
[00:24:02] y no me acuerdo que otros autores en 2012, 2013, 2018.
[00:24:05] 2012, 2013, 2018. Sí. Eh, pero era solo para evaluaciones
[00:24:09] Sí. Eh, pero era solo para evaluaciones sin genómica. Entonces lo que hicimos
[00:24:11] sin genómica. Entonces lo que hicimos fue justamente meterle genómica a eso y
[00:24:14] fue justamente meterle genómica a eso y aparte agregarle unas cositas más, por
[00:24:16] aparte agregarle unas cositas más, por ejemplo, no no se podía aproximar la
[00:24:19] ejemplo, no no se podía aproximar la verosimilitud, el valor de la
[00:24:21] verosimilitud, el valor de la verosimilitud. Bueno, también le
[00:24:22] verosimilitud. Bueno, también le agregamos eso, eh, le agregamos un
[00:24:26] agregamos eso, eh, le agregamos un average information remil más eficiente.
[00:24:29] average information remil más eficiente. Pero sí, es esa es una alternativa eh
[00:24:32] Pero sí, es esa es una alternativa eh que funciona tanto para datos grandes
[00:24:34] que funciona tanto para datos grandes como también para evitar esta inversión
[00:24:35] como también para evitar esta inversión que vos decías en
[00:24:38] que vos decías en una computadora más personal o un
[00:24:40] una computadora más personal o un ambiente computacional más restringido.
[00:24:44] ambiente computacional más restringido. Seguramente todo lo que trabajamos aquí
[00:24:45] Seguramente todo lo que trabajamos aquí en estadística y mi bello hermoso país
[00:24:48] en estadística y mi bello hermoso país Venezuela lo agradeceremos.
[00:24:51] Venezuela lo agradeceremos. Doctor, este es muy agradecido de poder
[00:24:55] Doctor, este es muy agradecido de poder compartir contigo, incluso he aprendido
[00:24:57] compartir contigo, incluso he aprendido muchísimo yo. Ya hay mucho más que leer,
[00:24:59] muchísimo yo. Ya hay mucho más que leer, mucho más que investigar. Muy ansioso
[00:25:01] mucho más que investigar. Muy ansioso para empezar esta lectura y nada más que
[00:25:03] para empezar esta lectura y nada más que darte las gracias y decirte que te
[00:25:05] darte las gracias y decirte que te despidas de de los seguidores y que des
[00:25:06] despidas de de los seguidores y que des tus palabras finales.
[00:25:09] tus palabras finales. No, agradezco mucho esta oportunidad.
[00:25:11] No, agradezco mucho esta oportunidad. Como como le decía antes a José, no
[00:25:14] Como como le decía antes a José, no conocía el canal, eh, pero la verdad que
[00:25:17] conocía el canal, eh, pero la verdad que tiene información muy buena y y bueno,
[00:25:19] tiene información muy buena y y bueno, esperemos que que se difunda mucho y y
[00:25:22] esperemos que que se difunda mucho y y que en Venezuela tengan más oportunidad
[00:25:24] que en Venezuela tengan más oportunidad de de salir al mundo, de interactuar con
[00:25:27] de de salir al mundo, de interactuar con el resto de los investigadores y y de
[00:25:29] el resto de los investigadores y y de seguir formándose también como lo hacen.
[00:25:32] seguir formándose también como lo hacen. Excelente, Matías, excelente. Bueno,
[00:25:34] Excelente, Matías, excelente. Bueno, muchas gracias y recuerden suscribirse
[00:25:36] muchas gracias y recuerden suscribirse al canal, darle like, compartir para más
[00:25:38] al canal, darle like, compartir para más videos y apoyar este canal de
[00:25:40] videos y apoyar este canal de estadísticas para adultos. Hasta la
[00:25:42] estadísticas para adultos. Hasta la próxima y saludos.