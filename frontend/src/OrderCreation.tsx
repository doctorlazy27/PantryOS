import { FormEvent, useEffect, useState } from 'react'
import { ShoppingCart } from 'lucide-react'
import { createSale, getProducts, Product } from './api'

type Props = { onToast: (message: string) => void }

export default function OrderCreation({ onToast }: Props) {
  const [products, setProducts] = useState<Product[]>([])
  const [customerName, setCustomerName] = useState('')
  const [product, setProduct] = useState('')
  const [quantity, setQuantity] = useState('')

  useEffect(() => {
    void getProducts().then((productData) => {
      setProducts(productData.products)
    }).catch(() => undefined)
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    try {
      const numericQuantity = Number(quantity)
      if (!Number.isFinite(numericQuantity) || numericQuantity < 1) { onToast('Enter a quantity greater than zero'); return }
      await createSale({ customer_name: customerName.trim(), items: [{ product_id: Number(product), quantity: numericQuantity }] })
      onToast('Sale recorded from your received stock')
    } catch (error) {
      onToast(error instanceof Error ? error.message : 'Could not create order')
    }
  }

  return <section className="panel workflow-card"><p className="eyebrow">Create order</p><h2>New sales order</h2><form className="form-grid" onSubmit={submit}><label>Customer name<input required value={customerName} placeholder="Enter any customer or company" onChange={(event) => setCustomerName(event.target.value)} /></label><label>Product<select required value={product} onChange={(event) => setProduct(event.target.value)}><option value="">Select product</option>{products.map((item) => <option key={item.product_id} value={item.product_id}>{item.name}</option>)}</select></label><label>Quantity<input required type="number" min="1" value={quantity} placeholder="Enter quantity" onChange={(event) => setQuantity(event.target.value)} /></label><div className="form-actions"><button className="button primary" type="submit"><ShoppingCart size={16} /> Create order</button></div></form></section>
}
