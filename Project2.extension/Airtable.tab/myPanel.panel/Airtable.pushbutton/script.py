# -*- coding: utf-8 -*-
import json
import clr
import System
# Força o uso de UTF-8 sem tentar registar providers
System.Text.Encoding.UTF8


clr.AddReference("System.Net")

from System.Net import WebClient, HttpRequestHeader
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory
from Autodesk.Revit.DB import Transaction
from Autodesk.Revit.DB import BuiltInParameter
from pyrevit import forms
from pyrevit import script
from pyrevit.forms import WPFWindow
from Autodesk.Revit.UI import TaskDialog, TaskDialogCommandLinkId, TaskDialogCommonButtons, TaskDialogResult
from System.Collections.ObjectModel import ObservableCollection

clr.AddReference("System")


doc = __revit__.ActiveUIDocument.Document

elements = FilteredElementCollector(doc)\
    .WhereElementIsNotElementType()\
    .ToElements()

valid_elements = []

for el in elements:
    # 1. Obter o tipo
    type_id = el.GetTypeId()
    if type_id == -1:
        continue

    element_type = doc.GetElement(type_id)
    if element_type is None:
        continue

    # 2. Verificar se o tipo tem Keynote
    key_param = element_type.LookupParameter("Keynote")
    if key_param is None:
        continue

    key = key_param.AsString()
    if not key:
        continue

    valid_elements.append(el)


client = WebClient()

AIRTABLE_BASE_ID="appc0KyzSKytG5ufI"
AIRTABLE_TABLE_NAME="tblxHzd5NlA10ZAiz"
AIRTABLE_API_KEY="patMwgCDTqH8uVrNz.2d7cda618ce886854cecfe27856adab9a7e05d60b229e5c8d5a5dfd4724e61b5"

url = "https://api.airtable.com/v0/{}/{}".format(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)

def make_request(description, keynote):    
    data = {
    "records": [
      {
        "fields": {
          "Description": description,
          "Keynote": keynote
        }
      }
    ]
  }

# GET dados do Airtable
client.Headers.Clear()
client.Headers.Add("Authorization", "Bearer {}".format(AIRTABLE_API_KEY))

response = client.DownloadString(url)
data = json.loads(response)


# Criar dicionário: Keynote → fields
airtable_data = {}

for rec in data["records"]:
    fields = rec.get("fields", {})
    if "Keynote" in fields:
        airtable_data[fields["Keynote"]] = fields

# Para evitar atualizar o mesmo tipo várias vezes
updated_types = set()

preview = []

for el in valid_elements:
    type_id = el.GetTypeId()
    element_type = doc.GetElement(type_id)

    # Keynote do tipo
    key_param = element_type.LookupParameter("Keynote")
    if not key_param:
        continue

    key = key_param.AsString()
    if not key or key not in airtable_data:
        continue

    info = airtable_data[key]

    # Description atual
    desc_param = element_type.LookupParameter("Description")
    current_desc = desc_param.AsString() if desc_param else None

    # Description nova
    new_desc = info.get("Description", None)

    # Nome do tipo
    type_name = element_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()

    # decidir se é nova alteração ou já atualizada
    if current_desc != new_desc:
        status = "novo"
    else:
        status = "historico"

    preview.append({
        "type_name": type_name,
        "keynote": key,
        "current": current_desc,
        "new": new_desc,
        "status": status
    })

class MainMenuWindow(WPFWindow):
    def __init__(self, xaml_file):
        WPFWindow.__init__(self, xaml_file)

        self.resultado = None

        self.BaseDadosBtn.Click += self.base_dados
        self.AlteracoesBtn.Click += self.alteracoes

    def base_dados(self, sender, args):
        self.resultado = "base"
        self.Close()

    def alteracoes(self, sender, args):
        self.resultado = "alteracoes"
        self.Close()

class AirtableRow(object):
    def __init__(self, id, keynote, description):
        self.Id = id
        self.Keynote = keynote
        self.Description = description

class DatabaseWindow(WPFWindow):
    def __init__(self, xaml_file, airtable_records):
        WPFWindow.__init__(self, xaml_file)
        print("XAML carregado com sucesso")


        self.records = airtable_records
        self.TabelaAirtable.ItemsSource = self.records

        # guardar IDs originais (antes de editar)
        self.original_ids = [item.Id for item in self.records if item.Id]

        self.AdicionarBtn.Click += self.adicionar
        self.RemoverBtn.Click += self.remover
        self.GuardarBtn.Click += self.guardar
        self.VoltarBtn.Click += self.voltar

        self.resultado = None

    def adicionar(self, sender, args):
        self.records.Add(AirtableRow(None, "", ""))

    def remover(self, sender, args):
        item = self.TabelaAirtable.SelectedItem
        if item:
            self.records.Remove(item)

    def guardar(self, sender, args):
        client = WebClient()
        client.Headers.Clear()
        client.Headers.Add("Authorization", "Bearer {}".format(AIRTABLE_API_KEY))
        client.Headers.Add("Content-Type", "application/json")

        # 1. IDs atuais (depois de editar)
        ids_atuais = set()
        for item in self.records:
            if item.Id:
                ids_atuais.add(item.Id)

        # 2. IDs originais (antes de editar)
        ids_originais = set(self.original_ids)

        # 3. Apagar registos removidos
        ids_para_apagar = ids_originais - ids_atuais
        for rid in ids_para_apagar:
            delete_url = url + "/" + rid
            client.UploadString(delete_url, "DELETE", "")

        # 4. Criar ou atualizar registos
        for item in self.records:
            fields = {
                "Keynote": item.Keynote,
                "Description": item.Description
            }


            if item.Id is None:
                payload = {"records": [{"fields": fields}]}
                body = json.dumps(payload, ensure_ascii=False)
                client.Encoding = System.Text.Encoding.UTF8
                print("POST:", body)
                response = client.UploadString(url, "POST", body)
                new_id = json.loads(response)["records"][0]["id"]
                item.Id = new_id
            else:
                payload = {"records": [{"id": item.Id, "fields": fields}]}
                body = json.dumps(payload, ensure_ascii=False)
                client.Encoding = System.Text.Encoding.UTF8
                print("PATCH:", body)
                print("Payload:", json.dumps(payload, ensure_ascii=False))
                client.UploadString(url, "PATCH", body)


        self.resultado = "guardar"
        self.Close()

    def voltar(self, sender, args):
        self.resultado = "voltar"
        self.Close()

class SelectorWindow(WPFWindow):
    def __init__(self, xaml_file):
        WPFWindow.__init__(self, xaml_file)

        self.resultado = None

        self.NovasBtn.Click += self.novas
        self.HistoricoBtn.Click += self.historico

    def novas(self, sender, args):
        self.resultado = "novas"
        self.Close()

    def historico(self, sender, args):
        self.resultado = "historico"
        self.Close()

# Carregar XAML
class PreviewWindow(WPFWindow):
    def __init__(self, xaml_file, dados):
        WPFWindow.__init__(self, xaml_file)

        self.AlteracoesGrid.ItemsSource = dados

        self.AplicarBtn.Click += self.aplicar
        self.CancelarBtn.Click += self.cancelar
        self.VoltarBtn.Click += self.voltar

        self.resultado = None

    def aplicar(self, sender, args):
        self.resultado = "aplicar"
        self.Close()

    def cancelar(self, sender, args):
        self.resultado = "cancelar"
        self.Close()

    def voltar(self, sender, args):
        self.resultado = "voltar"
        self.Close()

menu = MainMenuWindow("mainmenu.xaml")
menu.ShowDialog()

if menu.resultado == "base":
    # converter records do Airtable para lista editável
    records = ObservableCollection[AirtableRow]()

    for rec in data["records"]:
        fields = rec.get("fields", {})
        row = AirtableRow(
            rec["id"],
            fields.get("Keynote", ""),
            fields.get("Description", "")
        )
        records.Add(row)

    db = DatabaseWindow("database.xaml", records)
    db.ShowDialog()

    if db.resultado == "guardar":
        print("Alterações guardadas no Airtable")

    script.exit()  # depois de gerir base de dados, termina o script
 # depois de gerir base de dados, termina o script

elif menu.resultado == "alteracoes":
    # 👉 Só aqui é que seguimos para o selector + preview
    # Converter preview para objetos WPF-friendly
    class LinhaPreview(object):
        def __init__(self, tipo, keynote, atual, novo):
            self.Tipo = tipo
            self.Keynote = keynote
            self.Atual = atual
            self.Novo = novo

    novas = []
    historico = []

    for p in preview:
        linha = LinhaPreview(
            p["type_name"],
            p["keynote"],
            p["current"],
            p["new"]
        )

        if p["status"] == "novo":
            novas.append(linha)
        else:
            historico.append(linha)

    selector = SelectorWindow("selector.xaml")
    selector.ShowDialog()

    if selector.resultado == "novas":
        dados = novas
    elif selector.resultado == "historico":
        dados = historico
    else:
        script.exit()

    janela = PreviewWindow("ui.xaml", dados)
    janela.ShowDialog()

    if janela.resultado == "voltar":
        selector = SelectorWindow("selector.xaml")
        selector.ShowDialog()

        if selector.resultado == "novas":
            dados = novas
        elif selector.resultado == "historico":
            dados = historico
        else:
            script.exit()

        janela = PreviewWindow("ui.xaml", dados)
        janela.ShowDialog()

    if janela.resultado != "aplicar":
        script.exit()

else:
    script.exit()


# Criar lista de objetos
novas = []
historico = []

for p in preview:
    linha = LinhaPreview(
        p["type_name"],
        p["keynote"],
        p["current"],
        p["new"]
    )

    if p["status"] == "novo":
        novas.append(linha)
    else:
        historico.append(linha)

selector = SelectorWindow("selector.xaml")
selector.ShowDialog()

if selector.resultado == "novas":
    dados = novas
elif selector.resultado == "historico":
    dados = historico
else:
    script.exit()

# Abrir janela
janela = PreviewWindow("ui.xaml", dados)
janela.ShowDialog()

# Decisão do utilizador
if janela.resultado == "voltar":
    # voltar ao selector
    selector = SelectorWindow("selector.xaml")
    selector.ShowDialog()

    if selector.resultado == "novas":
        dados = novas
    elif selector.resultado == "historico":
        dados = historico
    else:
        script.exit()

    # reabrir a janela principal com a nova escolha
    janela = PreviewWindow("ui.xaml", dados)
    janela.ShowDialog()

if janela.resultado != "aplicar":
    script.exit()

# ---- TRANSAÇÃO ÚNICA ----
t = Transaction(doc, "Update Types from Airtable")
t.Start()

try:
    for el in valid_elements:   # <--- AQUI ESTÁ A CORREÇÃO
        type_id = el.GetTypeId()
        if type_id in updated_types:
            continue  # já atualizámos este tipo

        element_type = doc.GetElement(type_id)
        if element_type is None:
            continue

        # Ler Keynote do tipo
        key_param = element_type.LookupParameter("Keynote")
        if not key_param:
            continue

        key = key_param.AsString()
        if not key:
            continue

        # Verificar se existe no Airtable
        if key not in airtable_data:
            continue

        info = airtable_data[key]

        # Atualizar Description do tipo
        desc_param = element_type.LookupParameter("Description")
        if desc_param and "Description" in info:
            desc_param.Set(info["Description"])
            type_name = element_type.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString()

        updated_types.add(type_id)

    t.Commit()

except Exception as e:
    print("Erro:", e)
    t.RollBack()
